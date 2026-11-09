"""Step 02 -- THE TEST EVALUATION. Run exactly once.

Only the variant selected on TRAIN (V4) is evaluated on TEST, unchanged. The other four
declared variants are deliberately NOT evaluated here, so "TEST touched once" is literally
true. References and the negative control run in the same window for comparison.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from common import (
    TEST,
    build_score,
    build_signal,
    buy_and_hold,
    composite_score,
    panel,
    random_control,
    roc_panel,
    row,
    run,
    slice_w,
    table,
    yearly_series,
)

OUT: dict = {"window": TEST, "selected": None}
N_SEEDS = 20


def main() -> None:
    px = panel()

    with open("train_result.json") as fh:
        tr = json.load(fh)
    sel_name = tr["selected"]
    spec = tr["variants"][sel_name]
    OUT["selected"] = spec
    period, threshold = spec["period"], spec["threshold"]

    n_test = int(((px.index >= pd.Timestamp(TEST[0], tz=px.index.tz))
                  & (px.index <= pd.Timestamp(TEST[1], tz=px.index.tz))).sum())
    print("=" * 96)
    print(f"STEP 02 -- TEST  {TEST[0]} -> {TEST[1]}  ({n_test} bars)")
    print(f"  selected on TRAIN: {sel_name}  (roc period={period}, threshold={threshold})")
    print("=" * 96)

    sig = build_signal(px, period, threshold)
    score = build_score(px, sig)
    res = run(px, score, TEST)
    m = res.metrics
    OUT["strategy"] = {**row(sel_name, m, res)}
    OUT["strategy"]["detail"] = {
        "vol": m.volatility, "total": m.total_return, "winrate": m.win_rate,
        "best_day": m.best_day, "worst_day": m.worst_day,
        "maxdd_days": m.max_drawdown_days, "n_rebalances": res.diag["n_rebalances"],
        "cost_paid_rs": res.costs_paid, "capital_rs": 2_100_000.0,
        "cost_paid_pct_capital": res.costs_paid / 2_100_000.0,
        "round_trip_bps": res.diag["round_trip_bps"],
        "yearly": {int(k): float(v) for k, v in yearly_series(res.returns).items()},
    }
    OUT["strategy"]["equity"] = {str(d.date()): float(v)
                                 for d, v in res.equity.resample("W-FRI").last().dropna().items()}

    # --- references, identical window / engine / costs
    comp = run(px, composite_score(px), TEST)
    OUT["composite"] = {**row("composite", comp.metrics, comp)}
    OUT["buy_hold"] = {**row("buy_and_hold", buy_and_hold(px, TEST))}
    OUT["buy_hold"]["yearly"] = {int(k): float(v)
                                 for k, v in yearly_series(slice_equity(px, TEST)).items()}

    # --- liveness on TEST (reporting only; no re-tuning happens after this)
    roc = roc_panel(px, period)
    from common import signal_liveness
    live = signal_liveness(slice_w(sig, TEST), slice_w(roc, TEST), threshold)
    OUT["liveness_test"] = live

    print()
    print(table([OUT["strategy"], OUT["composite"], OUT["buy_hold"]]))
    d = OUT["strategy"]["detail"]
    print(f"\n  detail: total {d['total'] * 100:+.2f}% | vol {d['vol'] * 100:.2f}% | "
          f"win {d['winrate'] * 100:.1f}% | best {d['best_day'] * 100:+.2f}% | "
          f"worst {d['worst_day'] * 100:+.2f}%")
    print(f"  maxDD {m.max_drawdown * 100:.2f}% over {d['maxdd_days']} trading days | "
          f"{d['n_rebalances']:.0f} rebalances")
    print(f"  costs paid Rs {d['cost_paid_rs']:,.0f} on Rs {d['capital_rs']:,.0f} "
          f"= {d['cost_paid_pct_capital'] * 100:.2f}% of capital")
    print("  yearly: " + "  ".join(f"{k} {v * 100:+.2f}%" for k, v in d["yearly"].items()))
    print(f"  liveness on TEST: long {live['frac_bars_long'] * 100:.1f}% of symbol-bars, "
          f"{live['mean_flagged_per_day']:.1f} flagged/day, "
          f"{live['days_zero_flagged']} all-empty days")

    # --- negative control: coin flip with the same % of bars long
    print("\n" + "-" * 96)
    print(f"NEGATIVE CONTROL -- {N_SEEDS} random seeds each, matched to "
          f"{live['frac_bars_long'] * 100:.1f}% bar-liveness")
    print("-" * 96)
    ctrl = {}
    for mode in ("gate", "score"):
        rs = [random_control(px, live["frac_bars_long"], TEST, seed=1000 + i, mode=mode)
              for i in range(N_SEEDS)]
        cagr = np.array([r.metrics.cagr for r in rs])
        shp = np.array([r.metrics.sharpe for r in rs])
        dd = np.array([r.metrics.max_drawdown for r in rs])
        ctrl[mode] = {
            "cagr_mean": float(cagr.mean()), "cagr_min": float(cagr.min()),
            "cagr_max": float(cagr.max()), "sharpe_mean": float(shp.mean()),
            "sharpe_min": float(shp.min()), "sharpe_max": float(shp.max()),
            "maxdd_mean": float(dd.mean()),
            "beats_cagr": int((cagr > m.cagr).sum()), "beats_sharpe": int((shp > m.sharpe).sum()),
        }
        print(f"  random {mode:<6}: CAGR {cagr.mean() * 100:6.2f}% "
              f"[{cagr.min() * 100:6.2f}, {cagr.max() * 100:6.2f}] | "
              f"Sharpe {shp.mean():6.2f} [{shp.min():5.2f}, {shp.max():5.2f}] | "
              f"MaxDD {dd.mean() * 100:6.2f}% | beats strategy on CAGR "
              f"{ctrl[mode]['beats_cagr']}/{N_SEEDS}, Sharpe {ctrl[mode]['beats_sharpe']}/{N_SEEDS}")
    print(f"  {'STRATEGY':<14}: CAGR {m.cagr * 100:6.2f}% {'':>26}| "
          f"Sharpe {m.sharpe:6.2f} {'':>22}| MaxDD {m.max_drawdown * 100:6.2f}%")
    OUT["control"] = ctrl

    # --- zero/double/triple cost sensitivity on TEST
    print("\n" + "-" * 96)
    print("COST SENSITIVITY (TEST)")
    print("-" * 96)

    from nsealgo.costs import CostModel
    OUT["cost_sens"] = {}
    for sl, lbl in ((0, "zero"), (5, "base"), (10, "double"), (15, "triple")):
        cm = CostModel(segment="delivery", slippage_bps=sl)
        r2 = run(px, score, TEST, cost_model=cm)
        OUT["cost_sens"][lbl] = {**row(f"slip{lbl}", r2.metrics, r2)}
        print(f"  {lbl:<7} ({sl:>2} bps/side): CAGR {r2.metrics.cagr * 100:6.2f}% | "
              f"Sharpe {r2.metrics.sharpe:6.2f} | MaxDD {r2.metrics.max_drawdown * 100:6.2f}% | "
              f"drag/y {r2.metrics.cost_drag_annual * 100:.2f}%")

    with open("test_result.json", "w") as fh:
        json.dump(OUT, fh, indent=2, default=float)
    print("\nwrote test_result.json")


def slice_equity(px, window):
    p = slice_w(px, window)
    r = p.pct_change(fill_method=None).fillna(0.0).mean(axis=1)
    return (1.0 + r).cumprod()


if __name__ == "__main__":
    main()
