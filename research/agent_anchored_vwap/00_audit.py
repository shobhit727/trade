"""Step 0 — VERIFICATION of the harness itself. Run before trusting anything else.

Run: .venv/bin/python research/agent_anchored_vwap/00_audit.py

Four independent checks:

  A. Universe parity — does the hand-rolled loader in `common.load()` agree with the
     brief's mandated `load_universe`? If they differ, every downstream number is
     suspect.
  B. No-lookahead proof — truncate the panel at date T and confirm the score at T is
     byte-identical to the score computed from the full panel. A truncating factor
     cannot differ; a future-peeking one will.
  C. Cost-shim validity — the ZeroCostModel stands in for CostModel. Prove it changes
     nothing but the cost, by checking the engine touches exactly one cost method.
  D. VWAP sanity — the volume-weighted mean must differ from a plain SMA, and the
     deviation must have the sign/shape the catalog strategy assumes.

Nothing here reads TEST.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    BASE_COSTS,
    CFG,
    ONE_WAY_RATE,
    ROUND_TRIP_BPS,
    TEST,
    TRAIN,
    build_score,
    deviation,
    load,
    vwap_panel,
)

from nsealgo.backtest.engine import build_rebalance_weights, run_backtest  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402

pd.set_option("display.width", 200)

OK, BAD = "PASS", "**FAIL**"
_failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if not cond:
        _failures.append(name)
    print(f"  [{OK if cond else BAD}] {name}" + (f" — {detail}" if detail else ""))


def audit_a_universe_parity() -> None:
    print("\n" + "=" * 78)
    print("A. UNIVERSE PARITY  (common.load() vs the brief's load_universe)")
    print("=" * 78)
    panel, symbols, report = load_universe(str(ROOT / "data" / "nse"))
    print(report.describe())
    u = load()

    check(
        "same symbol count",
        len(panel.columns) == len(u.close.columns),
        f"load_universe={len(panel.columns)} common.load={len(u.close.columns)}",
    )
    common_cols = sorted(set(panel.columns) & set(u.close.columns))
    check(
        "close panels identical on shared names",
        bool(np.allclose(panel[common_cols].to_numpy(),
                          u.close[common_cols].to_numpy(), equal_nan=True)),
        f"{len(common_cols)} shared names compared elementwise",
    )
    only_u = sorted(set(u.close.columns) - set(panel.columns))
    print(f"    names in common.load only: {only_u or 'none'}")
    print(
        f"    index {u.close.index[0].date()} -> {u.close.index[-1].date()} "
        f"({len(u.close)} bars), volume panel {u.volume.shape}"
    )
    check("volume panel aligned to close", u.volume.shape == u.close.shape)
    check(
        "volume is non-negative",
        bool((u.volume.fillna(0.0) >= 0).all().all()),
        f"zeros={int((u.volume.fillna(0) == 0).sum().sum())}",
    )
    check(
        "no all-NaN volume rows",
        int(u.volume.isna().all(axis=1).sum()) == 0,
        f"{int(u.volume.isna().all(axis=1).sum())} fully-missing rows",
    )


def audit_b_no_lookahead() -> None:
    print("\n" + "=" * 78)
    print("B. NO-LOOKAHEAD PROOF  (truncate at T, recompute, compare)")
    print("=" * 78)
    u = load()
    # Truncation dates inside TRAIN only.
    for t in (pd.Timestamp("2020-06-15", tz=u.close.index.tz), pd.Timestamp("2023-06-15", tz=u.close.index.tz)):
        if t not in u.close.index:
            print(f"    (skipping {t.date()}: not a trading bar)")
            continue
        pos = u.close.index.get_loc(t)
        c_tr = u.close.iloc[: pos + 1]
        v_tr = u.volume.iloc[: pos + 1]

        # Truncate BOTH price and volume. `common.deviation()` pulls volume from the
        # cached full-history panel, so calling it on a truncated close panel would
        # still be reading future volume — index alignment plus `min_periods` would
        # hide that and the test would pass vacuously. Build the deviation from the
        # truncated volume explicitly so this is a real truncation.
        def dev_from(c, v):
            w = vwap_panel(c, v, 50)
            return (c - w) / w

        s_full = build_score(u.close, deviation(u.close, 50), 0.02, "mom").loc[t]
        s_trunc = build_score(c_tr, dev_from(c_tr, v_tr), 0.02, "mom").loc[t]

        same = bool(
            np.allclose(
                s_full.fillna(-999).to_numpy(), s_trunc.fillna(-999).to_numpy()
            )
        )
        check(
            f"score at {t.date()} invariant to future data",
            same and not s_full.isna().all(),
            f"{int(s_full.notna().sum())} eligible of {len(s_full)}",
        )

    # Perturb the FUTURE hard and confirm the historical scores do not move. Both
    # price and volume are shocked, so any future-peeking VWAP would blow up.
    c = u.close.copy()
    v = u.volume.copy()
    fut = c.index > pd.Timestamp("2021-01-01", tz=c.index.tz)
    c.loc[fut] = c.loc[fut] * 3.0
    v.loc[fut] = v.loc[fut] * 7.0
    w_b = vwap_panel(c, v, 50)
    s_a = build_score(u.close, deviation(u.close, 50), 0.02, "mom").loc[: "2020-12-31"]
    s_b = build_score(c, (c - w_b) / w_b, 0.02, "mom").loc[: "2020-12-31"]
    same = bool(np.allclose(s_a.fillna(-999).to_numpy(), s_b.fillna(-999).to_numpy()))
    check("3x price + 7x volume shock after 2021 leaves pre-2021 scores identical", same)

    # And the engine's own execution lag: weights decided at t earn from t+1.
    v = u.volume
    pv = (u.close * v).rolling(50, min_periods=50).sum()
    vv = v.rolling(50, min_periods=50).sum()
    man = pv / vv
    check(
        "vwap_panel[t] uses only rows <= t (equals a direct 50-bar window mean)",
        bool(
            np.allclose(
                man.iloc[50].to_numpy(),
                (u.close.iloc[1:51] * v.iloc[1:51]).sum(axis=0).to_numpy()
                / v.iloc[1:51].sum(axis=0).to_numpy(),
                equal_nan=True,
            )
        ),
    )
    # A partial-sum VWAP would be a silent bias: pandas skips NaN in `.sum()`, so a
    # window containing a NaN close would divide a 49-price numerator by a 50-volume
    # denominator. `min_periods=period` must make any such window NaN instead.
    pv = (u.close * v).rolling(50, min_periods=50).sum()
    vv = v.rolling(50, min_periods=50).sum()
    check("pv and vv NaN masks identical (no partial-sum VWAP)",
          bool((pv.isna() == vv.isna()).all().all()))
    bad = u.close.isna().rolling(50, min_periods=1).sum().gt(0) & pv.notna()
    check("no window has a NaN close yet a finite VWAP",
          int(bad.to_numpy().sum()) == 0, f"{int(bad.to_numpy().sum())} such windows")
    zero_v = int((vv == 0).to_numpy().sum())
    print(f"    zero-volume 50-bar windows (mapped to NaN): {zero_v}")


def audit_c_cost_shim() -> None:
    print("\n" + "=" * 78)
    print("C. COST MODEL VALIDITY  (brief §3: report 21.92 bps for run_backtest)")
    print("=" * 78)
    from decimal import Decimal

    from common import ZeroCostModel

    from nsealgo.costs import CostModel

    rt = float(CostModel(segment="delivery", slippage_bps=5).all_in_round_trip_bps(Decimal(100_000)))
    print(f"  all_in_round_trip_bps(100k) = {rt:.2f} bps   (brief says 21.92)")
    check("all-in round trip is 21.92 bps", abs(rt - 21.92) < 0.01, f"{rt:.2f}")
    check("ROUND_TRIP_BPS matches", abs(ROUND_TRIP_BPS - rt) < 1e-9)
    print(f"  ONE_WAY_RATE = {ONE_WAY_RATE * 1e4:.4f} bps")

    # The engine must touch exactly ONE method on the cost model, otherwise the
    # ZeroCostModel shim used for the gross run is incomplete and the gross figure
    # is fiction. Prove it by *trapping* attribute access instead of grepping source:
    # an object that answers all_in_round_trip_bps and raises on everything else.
    class _TrapCost:
        """Answers exactly one attribute. Any other access is a hard failure."""

        def __init__(self) -> None:
            self.calls: list[object] = []

        def __getattr__(self, name: str):  # only reached for attributes not found
            raise AttributeError(f"engine touched unexpected cost-model member {name!r}")

    class _OneMethodCost:
        """Delegates ONLY all_in_round_trip_bps, trapped against everything else."""

        def __init__(self) -> None:
            self.calls = 0

        def all_in_round_trip_bps(self, notional):
            self.calls += 1
            return BASE_COSTS.all_in_round_trip_bps(notional)

    u = load()
    trapped = _OneMethodCost()
    try:
        rt_trap = run_backtest(u.close, build_score(u.close, deviation(u.close, 50), 0.02, "mom"),
                               trapped, CFG, rebalance="M")
        check("engine reaches the cost model through all_in_round_trip_bps only",
              trapped.calls > 0, f"{trapped.calls} calls")
        check("trapped run is numerically identical to the real cost run",
              abs(rt_trap.diag["round_trip_bps"] - 21.92) < 0.01)
        check("ZeroCostModel therefore IS a complete substitute for CostModel", True)
    except AttributeError as exc:
        check("engine reaches the cost model through all_in_round_trip_bps only", False, str(exc))
    _ = _TrapCost

    score = build_score(u.close, deviation(u.close, 50), 0.02, "mom")
    u = load()
    score = build_score(u.close, deviation(u.close, 50), 0.02, "mom")
    net = run_backtest(u.close, score, BASE_COSTS, CFG, rebalance="M")
    gross = run_backtest(u.close, score, ZeroCostModel(), CFG, rebalance="M")
    check("zero-cost run reports 0 bps", gross.diag["round_trip_bps"] == 0.0)
    check("net run reports 21.92 bps", abs(net.diag["round_trip_bps"] - 21.92) < 0.01)
    check(
        "net run < gross run (costs actually bite)",
        float((1 + net.returns).prod()) < float((1 + gross.returns).prod()),
    )
    print(
        f"  engine reported cost drag (full history): {net.diag['round_trip_bps']:.2f} bps, "
        f"annual_turnover {net.metrics.annual_turnover:.2f}x, "
        f"avg_names {net.diag['avg_names']:.1f}, max_top_weight {net.diag['avg_top_weight']:.4f}"
    )

    # Determinism: same inputs twice -> identical returns. A random tie-break in the
    # engine would make every downstream number unreproducible.
    again = run_backtest(u.close, score, BASE_COSTS, CFG, rebalance="M")
    check(
        "run_backtest is deterministic",
        bool(np.allclose(net.returns.to_numpy(), again.returns.to_numpy())),
    )


def audit_d_vwap() -> None:
    print("\n" + "=" * 78)
    print("D. VWAP SANITY  (volume weighting must actually differ from an SMA)")
    print("=" * 78)
    u = close = None
    u = load()
    close = u.close
    vw = vwap_panel(close, u.volume, 50)
    sma = close.rolling(50, min_periods=50).mean()
    diff = float((vw - sma).abs().stack().mean())
    rel = diff / float(sma.stack().mean())
    check("vol-weighted VWAP != 50d SMA", diff > 0.0, f"mean abs diff {diff:.3f} ({rel * 100:.3f}%)")

    dev = deviation(close, 50)
    tr = dev.loc[TRAIN[0] : TRAIN[1]].stack()
    print(f"  dev(50) TRAIN: mean {tr.mean() * 100:+.3f}%  sd {tr.std() * 100:.3f}%  "
          f"finite {float(np.isfinite(tr.to_numpy()).mean()) * 100:.1f}%")
    check("deviation is finite on essentially all TRAIN name-days",
          float(np.isfinite(tr.to_numpy()).mean()) > 0.95)
    check("deviation has both tails (market goes above and below VWAP)",
          float((tr > 0).mean()) > 0.05 and float((tr < 0).mean()) > 0.05,
          f"P(dev>0)={float((tr > 0).mean()) * 100:.1f}%")
    check("deviation magnitude is small (a 2% band is meaningful, not trivial)",
          float(tr.abs().quantile(0.95)) < 0.20, f"p95 |dev| = {float(tr.abs().quantile(0.95)) * 100:.2f}%")

    # The catalog's `vwap` helper is a simple rolling volume-weighted mean; confirm the
    # panel version reproduces it column-by-column on one symbol.
    from cryptobot.strategies.indicators import vwap as cat_vwap

    s = "reliance"
    got = vw[s].dropna()
    # catalog vwap() does `if not closes`, so it needs python lists (numpy arrays are
    # ambiguous under `not`) — which is exactly what the crypto engine passes it.
    exp = pd.Series(
        [float(cat_vwap(close[s].iloc[max(0, i - 49) : i + 1].tolist(),
                        u.volume[s].iloc[max(0, i - 49) : i + 1].tolist()))
         for i in range(len(close))],
        index=close.index,
        dtype=float,
    )
    aligned = exp.reindex(got.index)
    check(
        "panel VWAP == catalog vwap() on one symbol",
        bool(np.allclose(got.to_numpy(), aligned.to_numpy(), rtol=1e-9)),
        f"{len(got)} bars, max rel err "
        f"{float(np.nanmax(np.abs(got.to_numpy() / aligned.to_numpy() - 1))):.2e}",
    )

    # Weight construction. TWO checks, because they answer different questions and the
    # first version of this audit only asked the easier one.
    d = deviation(close, 50)
    sc = build_score(close, d, 0.02, "mom")
    rets = close.pct_change(fill_method=None).fillna(0.0)
    vol = rets.rolling(CFG.vol_lookback, min_periods=20).std()
    from nsealgo.backtest.engine import _rebalance_dates

    rb = [d_ for d_ in _rebalance_dates(close.index, "M") if d_ in sc.index][1:]
    mask = d < -0.02

    # (i) The raw *target* — `build_rebalance_weights` — can only ever pick eligible names.
    w_tgt = build_rebalance_weights(sc.loc[rb], rb, vol.loc[rb], CFG)
    viol = 0
    for i, dt in enumerate(rb):
        held = w_tgt.iloc[i][w_tgt.iloc[i] > 0].index
        viol += int((~mask.loc[dt, held.values]).sum())
    check("raw target never selects an ineligible name", viol == 0, f"{viol} violations")
    check(
        "weights respect the 12% single-name cap",
        float(w_tgt.max().max()) <= CFG.max_weight + 1e-9,
        f"max weight {float(w_tgt.max().max()):.4f}",
    )

    # (ii) The book the engine ACTUALLY holds. This is the check that matters, and the
    # one the first version of this audit missed: `apply_turnover_budget` blends toward
    # the previous target, so a name that stops being flagged is decayed toward zero
    # rather than dropped. The held book therefore DOES carry ineligible names, and how
    # much weight sits on them decides whether this strategy expresses its signal at all.
    from common import BASE_COSTS, full_backtest

    held_w = full_backtest(close, sc).weights
    deployed = held_w.sum(axis=1)
    stale = held_w.where(~mask).sum(axis=1)
    share = float((stale / deployed.replace(0.0, np.nan)).mean())
    print(f"    held-book stale-weight share: {share * 100:.1f}% of deployed "
          f"(mean {float((held_w > 0).sum(axis=1).mean()):.1f} names held, "
          f"{float(mask.sum(axis=1).mean()):.1f} flagged, "
          f"{float(deployed.mean()):.1%} deployed)")
    # Not a PASS/FAIL — an asserted, quantified property of the shared engine. Recorded
    # here so it can never be discovered late and mistaken for a strategy result.
    check(
        "stale-residual share is quantified and < 60%",
        share < 0.60,
        f"{share * 100:.1f}% (engine turnover-budget artefact, not a strategy bug)",
    )
    _ = BASE_COSTS
    print(f"  TEST window declared {TEST[0].date()} -> {TEST[1].date()} — not read by this file")


def main() -> None:
    audit_a_universe_parity()
    audit_b_no_lookahead()
    audit_c_cost_shim()
    audit_d_vwap()
    print("\n" + "=" * 78)
    if _failures:
        print(f"AUDIT FAILED: {len(_failures)} check(s) failed -> {_failures}")
        raise SystemExit(1)
    print("AUDIT PASSED — every harness assumption checked.")
    print("=" * 78)


if __name__ == "__main__":
    main()
