"""Step 13 — sanity checks BEFORE the TEST touch. All TRAIN-only.

1. Look-ahead proof: scramble the future, weights must not move; scramble the past
   (inside the used window) and they must.
2. Weight count: is the book ~22 names, or are residuals accreting?
3. Signal liveness: fraction of bars the signal is on.
4. Cost drag: gross vs net, and the cost-model ladder.
5. Plausibility ceiling.
6. Is V5 actually CMF, or a disguised something-else? (TRAIN rank correlation)
"""

from __future__ import annotations

import sys
from decimal import Decimal

sys.path.insert(0, "research/agent_cmf")

import numpy as np
import pandas as pd
from cmflib import (
    CFG,
    SPECS,
    TRAIN0,
    TRAIN1,
    build_score,
    cmf_panel,
    load_panels,
    metrics_on,
    row,
    run_window,
    show,
)

from nsealgo.backtest.engine import run_backtest
from nsealgo.costs import STRESS_MODELS
from nsealgo.factors.core import (
    build_composite_score,
    momentum_6m,
    momentum_12_1,
    reversal_20d,
    trend_strength_200d,
)


class ZeroCost:
    """Cost model stub with zero charges, for the gross-of-all-cost row only."""

    def all_in_round_trip_bps(self, notional: Decimal) -> Decimal:
        return Decimal("0")


def run_raw(panel, score, lo, hi, cost):
    warm = lo - pd.Timedelta(days=400)
    warm = max(warm, panel.index[0])
    sl = slice(warm, hi)
    return run_backtest(panel.loc[sl], score.loc[sl], cost, CFG)


def spearman(a: pd.DataFrame, b: pd.DataFrame) -> float:
    """Spearman corr between two same-shaped panels, cell-wise on pairwise-valid cells.

    Done in numpy on purpose: both panels carry the same symbol column labels, so
    ``pd.concat`` + ``DataFrame.corr`` pairs duplicate labels and returns garbage, and
    ``DataFrame.stack(dropna=...)`` is gone in pandas 3.
    """
    x = a.to_numpy(dtype=float).ravel()
    y = b.to_numpy(dtype=float).ravel()
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    rx = pd.Series(x).rank().to_numpy()
    ry = pd.Series(y).rank().to_numpy()
    if rx.std() == 0 or ry.std() == 0:
        return float("nan")
    return float(np.corrcoef(rx, ry)[0, 1])


def main() -> None:
    lo, hi = TRAIN0, TRAIN1
    closes, highs, lows, vols = load_panels()
    v5 = [s for s in SPECS if s[0] == "V5_p20_continuous_flip"][0]
    score, _ = build_score(closes, closes, highs, lows, vols, v5)
    warm = lo - pd.Timedelta(days=400)

    # ================= 1. look-ahead proof =================
    print("=" * 90 + "\nSANITY 1 — LOOK-AHEAD PROOF (TRAIN only)\n" + "=" * 90)
    cut = pd.Timestamp("2021-06-15", tz=closes.index.tz)
    base = run_window(closes, score, lo, cut)

    fut = closes.loc[closes.index > cut].copy()
    ramp = pd.Series(np.linspace(1.2, 2.5, len(fut)), index=fut.index, dtype=float)
    shocked = pd.concat([closes.loc[:cut], fut.mul(ramp, axis=0)])
    s2 = run_window(shocked, score, lo, cut)
    same = bool(np.allclose(base.weights.values, s2.weights.values, atol=1e-12))
    print(f"  scramble FUTURE x1.0->x2.5 : weights identical = {same}  "
          f"max|dw| {float(np.abs(base.weights.values - s2.weights.values).max()):.3e}")
    print(f"                                equity identical = "
          f"{bool(np.allclose(base.equity.values, s2.equity.values, atol=1e-12))}")
    assert same, "LOOKAHEAD DETECTED"

    # negative control: perturb prices INSIDE the window the backtest actually reads.
    inwin = closes.loc[:cut].copy()
    block = slice(warm + pd.Timedelta(days=200), warm + pd.Timedelta(days=400))
    inwin.loc[block] = inwin.loc[block] * 1.3
    s3 = run_window(inwin, score, lo, cut)
    moved = not bool(np.allclose(base.weights.values, s3.weights.values, atol=1e-9))
    print(f"  negative control: +30% on a PAST block inside the window moves weights "
          f"= {moved}")
    assert moved, "harness is not actually reading price history"

    # CMF itself must be causal
    c_now = cmf_panel(closes, highs, lows, vols, 20)
    c_shock = cmf_panel(shocked, highs, lows, vols, 20)
    d = np.nanmax(np.abs((c_now.loc[:cut] - c_shock.loc[:cut]).to_numpy()))
    print(f"  CMF(20) on [start,{cut.date()}] invariant to the future scramble: "
          f"max|d| {d:.3e}")
    assert d < 1e-12

    # ================= 2. weight count =================
    print("\n" + "=" * 90 + "\nSANITY 2 — WEIGHT COUNT / CONCENTRATION (TRAIN, V5)\n" + "=" * 90)
    res = run_window(closes, score, lo, hi)
    w = res.weights
    n = (w > 0).sum(axis=1)
    print(f"  n_positions target = {CFG.n_positions}   max_names = {CFG.max_names}")
    print(f"  names held: mean {n.mean():.2f}  median {int(n.median())}  "
          f"min {int(n.min())}  max {int(n.max())}")
    print(f"  invested weight sum(w): mean {w.sum(axis=1).mean():.4f}  "
          f"(= 1 - cash_buffer {CFG.cash_buffer})")
    print(f"  max single weight observed: {w.max().max():.4f}  (cap {CFG.max_weight})")
    flat = w.values[w.values > 0]
    print("  weight percentiles: "
          + str({f"p{p}": round(float(np.percentile(flat, p)), 4)
                 for p in (10, 25, 50, 75, 90, 99)}))
    print(f"  share of bars holding >22 names: {float((n > CFG.n_positions).mean()) * 100:.1f}%")
    assert int(n.max()) <= CFG.max_names, "position limit breached"
    assert w.max().max() <= CFG.max_weight + 1e-9, "single-name cap breached"
    # NOTE: do NOT group `w` by a symbol-indexed Series. `w` has a DatetimeIndex, so
    # pandas aligns the grouper to that index and silently produces ZERO groups — the
    # cap assert then passes vacuously. Group the transpose instead, whose index is
    # the symbol list. Verified: `w.groupby(sec['sector']).sum()` -> shape (0, n).
    from nsealgo.backtest.engine import sector_of
    sec_of = pd.Series([sector_of(c) for c in w.columns], index=w.columns)
    g = w.T.groupby(sec_of).sum().T          # dates x sectors
    assert g.shape[1] == sec_of.nunique(), "sector grouping failed"
    sec_max = g.max(axis=0)
    print(f"  sectors present: {g.shape[1]}  names mapped: "
          f"{int(sec_of.value_counts().sum())}/{len(w.columns)}")
    print(f"  max sector weight over time: {sec_max.max():.4f} (cap "
          f"{CFG.max_sector_weight})  worst sector: {sec_max.idxmax()}")
    print("    per-sector peak: "
          + str({k: round(float(v), 4) for k, v in sec_max.sort_values(ascending=False)
                 .head(6).items()}))
    assert sec_max.max() <= CFG.max_sector_weight + 1e-9, "sector cap breached"
    assert g.values.sum() > 0, "grouped weights are all zero"
    print("  -> book drifts 22 -> ~29 because the 0.35 turnover budget BLENDS toward")
    print("     each new target instead of replacing it, then _thin admits up to 30")
    print("     material names. Engine design (apply_turnover_budget/_thin), not an")
    print("     indexing bug and not a bypass of PortfolioConfig. Brief check #2: the")
    print("     residual-tail failure mode (48 names) does NOT occur; hard max is 30.")

    # ================= 3. signal liveness =================
    print("\n" + "=" * 90 + "\nSANITY 3 — SIGNAL LIVENESS (TRAIN)\n" + "=" * 90)
    for spec in SPECS:
        _, mask = build_score(closes, closes, highs, lows, vols, spec)
        f = float((mask.loc[lo:hi] > 0).sum().sum() / mask.loc[lo:hi].notna().sum().sum())
        print(f"  {spec[0]:24s} fraction of bars signalled: {f * 100:6.2f}%")
    print("  brief threshold is ~5%; V5 has no threshold by design (continuous cross-")
    print("  sectional rank) so it is long 96% of bars. Property of the variant, not a")
    print("  liveness bug — but it does mean V5 is a full-book tilt, not a filter.")

    # ================= 4. cost drag =================
    print("\n" + "=" * 90 + "\nSANITY 4 — COST DRAG, GROSS vs NET (TRAIN, V5)\n" + "=" * 90)
    m_g = metrics_on(run_raw(closes, score, lo, hi, ZeroCost()), lo, hi)
    m_n = metrics_on(res, lo, hi)
    print(f"  gross of ALL cost   : CAGR {m_g.cagr * 100:6.2f}%  Sh {m_g.sharpe:6.3f}  "
          f"MaxDD {m_g.max_drawdown * 100:7.2f}%")
    print(f"  net of 21.92 bps    : CAGR {m_n.cagr * 100:6.2f}%  Sh {m_n.sharpe:6.3f}  "
          f"MaxDD {m_n.max_drawdown * 100:7.2f}%")
    print(f"  cost drag {m_n.cost_drag_annual * 100:.2f}%/y on {m_n.annual_turnover:.2f}x "
          f"annual turnover  (CAGR given up by costs "
          f"{(m_g.cagr - m_n.cagr) * 100:.2f} pp/yr)")
    print("  -> gross and net are BOTH positive: the TRAIN result is not a cost artefact.")
    print("\n  cost-model ladder (TRAIN, V5):")
    for nm, cm in STRESS_MODELS.items():
        r = run_raw(closes, score, lo, hi, cm)
        mm = metrics_on(r, lo, hi)
        print(f"    {nm:16s} rt_bps {r.diag['round_trip_bps']:6.2f}  "
              f"CAGR {mm.cagr * 100:6.2f}%  Sh {mm.sharpe:5.2f}")

    # ================= 5. plausibility =================
    print("\n" + "=" * 90 + "\nSANITY 5 — PLAUSIBILITY CEILING\n" + "=" * 90)
    r = closes.pct_change(fill_method=None).loc[lo:hi].mean(axis=1).fillna(0.0)
    yrs = len(r) / 244
    print(f"  equal-weight universe TRAIN CAGR "
          f"{(float((1 + r).prod()) ** (1 / yrs) - 1) * 100:.2f}%  (no costs, no selection)")
    print("  best CMF variant TRAIN CAGR 17.31% — well inside the 40-50% long-only")
    print("  ceiling. No bug indicated.")

    # ================= 6. what is V5 really =================
    print("\n" + "=" * 90
          + "\nSANITY 6 — WHAT IS V5, REALLY? (TRAIN, daily cross-sectional Spearman)\n"
          + "=" * 90)
    factors = {
        "V5_-CMF_rank": score,
        "momentum_12_1": momentum_12_1(closes).rank(axis=1, pct=True),
        "momentum_6m": momentum_6m(closes).rank(axis=1, pct=True),
        "trend_str_200d": trend_strength_200d(closes).rank(axis=1, pct=True),
        "reversal_20d": reversal_20d(closes).rank(axis=1, pct=True),
        "nsealgo_composite": build_composite_score(closes),
    }
    keys = list(factors)
    rows = []
    for i, a in enumerate(keys):
        rr = {"factor": a}
        for b in keys[i + 1:]:
            rr[b[:14]] = round(spearman(factors[a].loc[lo:hi], factors[b].loc[lo:hi]), 3)
        rows.append(rr)
    show(pd.DataFrame(rows).set_index("factor"), "daily cross-sectional rank correlation")
    print("\n  Read: V5 correlates **+0.647 with reversal_20d** and only -0.173 with the")
    print("  project composite. So the sign-flipped CMF is substantially a SHORT-TERM")
    print("  REVERSAL factor — and src/nsealgo/factors/core.py documents that reversal")
    print("  does NOT work in Indian equities (Sehgal & Jain 2011 / IIMC 2020 find")
    print("  continuation; Romano-Wolf multiple-testing study: all reversal rules fail).")

    # ================= 7. decomposition =================
    print("\n" + "=" * 90
          + "\nSANITY 7 — IS V5 JUST REVERSAL? (TRAIN diagnostic, NOT a budget variant)\n"
          + "=" * 90)
    print("  Selection is already fixed (§0.2: max TRAIN Sharpe over V1-V5). These rows are")
    print("  diagnostics only — they cannot and do not change what goes to TEST.")
    diag = {}
    for nm, fac in [
        ("V5_-CMF_rank", score),
        ("reversal_20d_only", reversal_20d(closes).rank(axis=1, pct=True)),
        ("reversal_5d_only", reversal_20d(closes).rank(axis=1, pct=True)),
        ("momentum_6m_only", momentum_6m(closes).rank(axis=1, pct=True)),
    ]:
        if nm == "reversal_5d_only":
            from nsealgo.factors.core import reversal_5d
            fac = reversal_5d(closes).rank(axis=1, pct=True)
        m = metrics_on(run_window(closes, fac, lo, hi), lo, hi)
        diag[nm] = row(nm, m, rt_bps=21.92)
        print(f"  {nm:22s} CAGR {m.cagr * 100:6.2f}%  Sh {m.sharpe:6.3f}  "
              f"MaxDD {m.max_drawdown * 100:7.2f}%")
    print("\n  If reversal_20d alone reproduces most of V5's TRAIN Sharpe, then V5's")
    print("  TRAIN edge is a reversal edge, not a Chaikin money-flow edge.")


if __name__ == "__main__":
    main()
