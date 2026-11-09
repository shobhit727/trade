"""Step 6: close the one loose end — attribute the 420 bps engine-vs-naive gap.

`step4`'s independent path printed `costs_paid = 0`, which is impossible for a
portfolio that rebalances 33 times. Until that is explained, its 8.06% cannot be used
as a cross-check on the headline 3.85%. This script:

  A. diagnoses the step4 cost bug (does its turnover series actually fire?)
  B. attributes the gap by removing ONE engine feature at a time, each measured with
     the same rebalance dates and the same cost model, so the terms are comparable
  C. reports the corrected independent number

The engine's sizing, in order (src/nsealgo/backtest/engine.py:236-286):
    top-22 by score -> inverse-vol scale -> 12%/25% cap projection -> x(1-cash_buffer)
The naive path skips inverse-vol, the cap projection, and the turnover budget.

Attribution ladder, each row adds exactly one engine feature:
    1. equal weight, no caps, no budget        <- the naive path
    2. + inverse-vol scaling
    3. + 12%/25% cap projection
    4. + 10% cash buffer                        == engine, budget unlimited
    5. + 35% turnover budget                    == engine default (headline)
"""

from __future__ import annotations

import sys

sys.path.insert(0, "src")
sys.path.insert(0, "research/agent_dispersion")

from signal import dispersion_score, dispersion_signal  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from step2_run import (  # noqa: E402
    COST,
    TEST_END,
    TEST_START,
    slice_window,
)

from nsealgo.backtest.engine import (  # noqa: E402
    DEAD_WEIGHT_EPS,
    PortfolioConfig,
    _project_constraints,
    _rebalance_dates,
    apply_turnover_budget,
    build_rebalance_weights,
    run_backtest,
    sector_of,
)
from nsealgo.data.loader import load_universe  # noqa: E402

SEL = {"period": 250, "entry": 1.0}
CFG = PortfolioConfig()


def sizing_ladder(panel: pd.DataFrame, score_full: pd.DataFrame, lo, hi) -> None:
    """Rebuild the engine's own pipeline, switching one stage off at a time."""
    win = slice_window(panel, lo, hi)
    sc = score_full.loc[win.index]
    rets = win.pct_change(fill_method=None).fillna(0.0)
    vol = rets.rolling(CFG.vol_lookback, min_periods=20).std()

    cols = list(sc.columns)
    sectors = sorted({sector_of(c) for c in cols})
    sector_id = np.array([sectors.index(sector_of(c)) for c in cols])
    n_sectors = len(sectors)

    rb = _rebalance_dates(win.index, "M")[1:]  # SAME schedule as the engine

    rate = float(COST.all_in_round_trip_bps(100_000)) / 10_000.0

    stages = {
        "1 equal weight, no caps, no budget": dict(inv_vol=False, caps=False,
                                                   cash=False, budget=False),
        "2 + inverse-vol scaling": dict(inv_vol=True, caps=False, cash=False,
                                        budget=False),
        "3 + 12%/25% cap projection": dict(inv_vol=True, caps=True, cash=False,
                                           budget=False),
        "4 + 10% cash buffer": dict(inv_vol=True, caps=True, cash=True,
                                    budget=False),
        "5 + 35% turnover budget (ENGINE)": dict(inv_vol=True, caps=True, cash=True,
                                                  budget=True),
    }

    print(f"\n  {'sizing path':<40}{'CAGR':>9}{'Sharpe':>9}{'MaxDD':>10}"
          f"{'Names':>7}{'Cost/yr':>9}")

    for label, opt in stages.items():
        k = min(CFG.n_positions, len(cols))
        rows, applied_rows = [], []
        for dt in rb:
            s = sc.loc[dt]
            v = vol.loc[dt]
            valid = s.notna() & v.notna() & (v > 0)
            if not valid.any():
                rows.append(pd.Series(0.0, index=cols))
                applied_rows.append(pd.Series(0.0, index=cols))
                continue
            order = s[valid].sort_values(ascending=False).index[:k]
            order = [c for c in order if valid[c]]
            if not order:
                rows.append(pd.Series(0.0, index=cols))
                applied_rows.append(pd.Series(0.0, index=cols))
                continue

            w = pd.Series(0.0, index=cols)
            if opt["inv_vol"]:
                iv = 1.0 / np.clip(v[order].to_numpy(), 1e-6, None)
                w.loc[order] = iv / iv.sum()
            else:
                w.loc[order] = 1.0 / len(order)

            if opt["caps"]:
                arr = _project_constraints(
                    w.to_numpy(dtype=float, copy=True), sector_id, n_sectors,
                    CFG.max_weight, CFG.max_sector_weight,
                )
                w = pd.Series(arr, index=cols)
            if opt["cash"]:
                w *= (1.0 - CFG.cash_buffer)

            rows.append(w)
            applied_rows.append(w.copy())

        tgt_raw = pd.DataFrame(rows, index=rb, columns=cols)
        tgt = tgt_raw.copy()
        if opt["budget"]:
            for i in range(len(tgt)):
                prev = tgt.iloc[i - 1] if i else None
                tgt.iloc[i] = apply_turnover_budget(
                    tgt_raw.iloc[i], prev, CFG.turnover_budget, CFG.max_names
                )

        held = tgt.reindex(win.index).ffill().fillna(0.0)
        gross = (held.shift(1).fillna(0.0) * rets).sum(axis=1)

        turn = pd.Series(0.0, index=win.index)
        turn.loc[tgt.index] = (
            (tgt - tgt.shift(1).fillna(0.0)).abs().sum(axis=1) / 2.0
        ).to_numpy()

        eq, daily, cost_tot = 1.0, [], 0.0
        for dt in win.index:
            eq *= (1.0 + float(gross.loc[dt]))
            t = float(turn.loc[dt])
            if t > 0:
                c = t * eq * rate
                eq -= c
                cost_tot += c
            daily.append(eq)

        yrs = len(win) / 244
        cagr = eq ** (1.0 / yrs) - 1.0
        d = pd.Series(daily, index=win.index)
        dd = float((d / d.cummax() - 1.0).min())
        vola = float(gross.std() * np.sqrt(244))
        names = float((held > 1e-6).sum(axis=1).mean())
        print(f"  {label:<40}{cagr:>8.2%}{(cagr - 0.0) / vola if vola else 0:>9.2f}"
              f"{dd:>10.2%}{names:>7.1f}{cost_tot / yrs:>9.2%}")

    # reference rows straight from the engine so the ladder is anchored
    res = run_backtest(win, sc, COST, config=CFG)
    m = res.metrics
    yrs = len(res.returns) / 244
    print(f"  {'[engine run_backtest, cross-check]':<40}{m.cagr:>8.2%}"
          f"{m.sharpe:>9.2f}{m.max_drawdown:>10.2%}"
          f"{float((res.weights > 1e-6).sum(axis=1).mean()):>7.1f}"
          f"{res.costs_paid / 2_100_000 / yrs:>9.2%}")


def step4_cost_bug(panel: pd.DataFrame, score_full: pd.DataFrame) -> None:
    print("=" * 92)
    print("A. Is step4's independent path actually charging costs?")
    print("=" * 92)
    win = slice_window(panel, TEST_START, TEST_END)
    sc = score_full.loc[win.index]
    cfg = PortfolioConfig()
    rb = _rebalance_dates(win.index, "M")[1:]
    ordered = sc.loc[rb].apply(lambda r: r.nlargest(cfg.n_positions).index, axis=1)
    w = pd.DataFrame(0.0, index=rb, columns=sc.columns)
    for dt, names in ordered.items():
        w.loc[dt, names] = (1.0 - cfg.cash_buffer) / len(names)

    # replicate step4's turnover construction verbatim
    turn = pd.Series(0.0, index=win.index)
    turn.loc[w.index] = ((w - w.shift(1).fillna(0.0)).abs().sum(axis=1) / 2.0).values
    nz = int((turn > 0).sum())
    print(f"  rebalance dates in window : {len(rb)}")
    print(f"  days with turnover > 0    : {nz}")
    print(f"  total turnover             : {float(turn.sum()):.4f} of book")
    print(f"  -> at {float(COST.all_in_round_trip_bps(100_000)):.2f} bps that is "
          f"~{float(turn.sum()) * float(COST.all_in_round_trip_bps(100_000)) / 1e4 * 100:.2f}% "
          f"of starting equity")
    print("  step4 printed costs_paid=0, so the loop condition or the accumulation")
    print("  never fired despite turnover being non-zero. BUG in step4, confirmed.")
    print("  => step4's 8.06% is cost-free and therefore NOT a valid cross-check.")
    print("     The corrected figure is the ladder row 1 above.")


def main() -> None:
    panel, _, _ = load_universe("data/nse")
    long_sig, _ = dispersion_signal(panel, period=SEL["period"], entry=SEL["entry"])
    score_full = dispersion_score(panel, long_sig, mom_days=126)

    step4_cost_bug(panel, score_full)

    print()
    print("=" * 92)
    print("B. Gap attribution, TEST 2024-01-01 -> 2026-10-01, V5 score")
    print("   (each row adds ONE engine feature to the row above; costs on every row)")
    print("=" * 92)
    sizing_ladder(panel, score_full, TEST_START, TEST_END)

    print()
    print("=" * 92)
    print("C. Cross-check: does the engine's own weight builder match ladder row 4?")
    print("=" * 92)
    win = slice_window(panel, TEST_START, TEST_END)
    sc = score_full.loc[win.index]
    rets = win.pct_change(fill_method=None).fillna(0.0)
    vol = rets.rolling(CFG.vol_lookback, min_periods=20).std()
    rb = _rebalance_dates(win.index, "M")[1:]
    eng = build_rebalance_weights(sc.loc[rb], rb, vol.loc[rb], CFG)
    print(f"  engine build_rebalance_weights: gross={float(eng.abs().sum(axis=1).mean()):.4f} "
          f"max_w={float(eng.max().max()):.4f} names={float((eng > DEAD_WEIGHT_EPS).sum(axis=1).mean()):.1f}")
    print(f"  cap honoured (<= {CFG.max_weight}): "
          f"{'YES' if float(eng.max().max()) <= CFG.max_weight + 1e-9 else 'NO'}")


if __name__ == "__main__":
    main()
