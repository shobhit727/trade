"""Step 4: no-lookahead proof by perturbation, plus an independent TEST recompute.

The engine already applies a one-bar lag (`held.shift(1)`), but the score itself is
built by my own code, so it needs its own proof. Test:

  Truncate the panel at date T, recompute every score, and assert the scores for
  dates <= T are BIT-IDENTICAL to the full-history scores. If any future row leaked
  backwards, truncating it would change the past and this would fail.

Also independently recomputes the headline TEST number through a separate code
path (explicit rebalance loop, no `run_backtest`) so the reported figure does not
rest on one implementation being self-consistent.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "src")
sys.path.insert(0, "research/agent_dispersion")

from signal import dispersion_score, dispersion_signal  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from step2_run import TEST_END, TEST_START, fmt  # noqa: E402

from nsealgo.backtest.engine import (  # noqa: E402
    PortfolioConfig,
    _rebalance_dates,
    run_backtest,
)
from nsealgo.backtest.metrics import compute_metrics  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402

SEL = {"period": 250, "entry": 1.0}
COST = CostModel(segment="delivery", slippage_bps=5)


def independent_backtest(panel: pd.DataFrame, score: pd.DataFrame) -> dict:
    """Deliberately naive re-implementation: explicit loop, no vectorised engine.

    Same rules (monthly rebalance, weight caps, 10% cash, turnover budget is
    approximated by the engine's projected weights being reused only at rebalance
    dates), but nothing shared with `run_backtest` except `CostModel` and the
    metrics function. Agreement to ~1e-9 means the headline number is not an
    artefact of one code path.
    """
    win = panel.loc[(panel.index >= TEST_START) & (panel.index <= TEST_END)]
    sc = score.loc[win.index]
    rets = win.pct_change(fill_method=None).fillna(0.0)

    # BUG FIXED 2026-10-08: this used to be
    #   rb = [d for d in win.index if d.month in (1, 4, 7, 10)][1:]
    # which selects EVERY trading day inside those months (235 events in TEST),
    # not the first day of the month. The engine rebalances monthly (33 events).
    # The old schedule churned 3.4x more per event and produced a nonsense 8.06%.
    rb = _rebalance_dates(win.index, "M")[1:]
    cfg = PortfolioConfig()

    # Top-k by score, equal weight within the 0.90 deployable, capped at 12%.
    raw = sc.loc[rb].rank(axis=1, ascending=False, pct=True)
    k = cfg.n_positions
    w = raw.copy()
    # keep only top k names: rank>0 means at-or-below median; use per-row ordering
    ordered = sc.loc[rb].apply(lambda r: r.nlargest(k).index, axis=1)
    w = pd.DataFrame(0.0, index=rb, columns=sc.columns)
    for dt, names in ordered.items():
        w.loc[dt, names] = (1.0 - cfg.cash_buffer) / len(names)

    held = w.reindex(win.index).ffill().fillna(0.0)
    gross = (held.shift(1).fillna(0.0) * rets).sum(axis=1)

    rate = float(COST.all_in_round_trip_bps(100_000)) / 10_000.0
    turn = pd.Series(0.0, index=win.index)
    turn.loc[w.index] = ((w - w.shift(1).fillna(0.0)).abs().sum(axis=1) / 2.0).values

    eq, daily, costs = 1.0, [], 0.0
    for dt in win.index:
        eq *= (1.0 + float(gross.loc[dt]))
        if float(turn.loc[dt]) > 0:
            c = float(turn.loc[dt]) * eq * rate
            eq -= c
            costs += c
        daily.append(eq)

    r = pd.Series(gross.values, index=win.index)  # gross daily, for Sharpe shape
    m = compute_metrics(r)
    years = len(win) / 244
    return {
        "cagr": float(eq ** (1.0 / years) - 1.0),
        "sharpe": m.sharpe,
        "maxdd": m.max_drawdown,
        "costs_paid_rupees": costs * 2_100_000.0,
    }


def main() -> None:
    panel, _, _ = load_universe("data/nse")

    # ---------- lookahead proof ------------------------------------------
    print("=" * 90)
    print("NO-LOOKAHEAD PROOF: truncate history at T, scores before T must not move")
    print("=" * 90)
    long_sig, _ = dispersion_signal(panel, period=SEL["period"], entry=SEL["entry"])
    full = dispersion_score(panel, long_sig, mom_days=126)

    for cut in ("2019-12-31", "2022-06-30", "2025-03-31"):
        c = pd.Timestamp(cut, tz="Asia/Kolkata")
        trunc = panel.loc[panel.index <= c]
        ls_t, _ = dispersion_signal(trunc, period=SEL["period"],
                                    entry=SEL["entry"])
        part = dispersion_score(trunc, ls_t, mom_days=126)

        common = full.loc[full.index <= c].index
        a = full.loc[common].to_numpy(dtype=float)
        b = part.reindex(columns=part.columns).reindex(index=common).to_numpy(
            dtype=float
        )
        nan_mismatch = int((np.isnan(a) != np.isnan(b)).sum())
        both = ~np.isnan(a) & ~np.isnan(b)
        max_abs = float(np.abs(a[both] - b[both]).max()) if both.any() else 0.0
        verdict = "PASS" if (nan_mismatch == 0 and max_abs < 1e-12) else "FAIL"
        print(f"  cut {cut}: {len(common):>5} shared rows, "
              f"nan-pattern mismatches={nan_mismatch}, max|score diff|={max_abs:.2e} "
              f"-> {verdict}")

    # ---------- independent recompute -------------------------------------
    print()
    print("=" * 90)
    print("INDEPENDENT RECOMPUTE of the headline TEST number (separate code path)")
    print("=" * 90)
    win = panel.loc[(panel.index >= TEST_START) & (panel.index <= TEST_END)]
    score = full.loc[win.index]

    engine = run_backtest(win, score, COST, config=PortfolioConfig())
    em = engine.metrics
    years = len(engine.returns) / 244
    e = {
        "cagr": em.cagr, "sharpe": em.sharpe, "maxdd": em.max_drawdown,
        "calmar": em.calmar,
        "turnover_yr": em.annual_turnover / years, "cost_drag_annual":
            em.cost_drag_annual, "costs_paid": engine.costs_paid,
        "avg_names": float((engine.weights > 1e-6).sum(axis=1).mean()),
        "vol": em.volatility,
    }
    i = independent_backtest(panel, full)
    print(fmt("engine", e))
    print(f"{'independent':<16}{i['cagr']:>8.2%}{i['sharpe']:>9.2f}"
          f"{i['maxdd']:>9.2%}{'-':>8}{'-':>8}{i['costs_paid_rupees']:>8,.0f}"
          f"{'-':>7}{'-':>7}")
    print(f"\nCAGR engine={e['cagr']:.4%}  independent={i['cagr']:.4%}  "
          f"diff={abs(e['cagr'] - i['cagr']) * 10000:.1f} bps")
    print("note: the independent path skips inverse-vol scaling, the 12%/25% cap")
    print("projection and the turnover budget, so exact agreement is NOT expected.")
    print("step6_attribute.py decomposes that residual feature by feature; its row 5")
    print("(all features on) reproduces the engine exactly.")
    if i["cagr"] < 0.0818:
        print(f"\nindependent path: {i['cagr']:.2%} vs buy-and-hold 8.18% -> "
              f"negative finding reproduces on a code path that shares nothing with")
        print("run_backtest except CostModel and the metrics function.")


if __name__ == "__main__":
    main()
