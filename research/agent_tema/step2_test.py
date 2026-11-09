"""Step 2 -- TEST evaluation. Touched EXACTLY ONCE, on the frozen V4.

`selected.json` was written by step1 from TRAIN data only. This script reads it, does
not write it, and evaluates exactly that variant on 2024-01-01 -> 2026-10-01.

Also computed in the same pass (all required by the brief, none of them a parameter
choice):
  * buy-and-hold over the identical window, same 21.92 bps
  * random-signal control at the same long-fraction, several seeds
  * nsealgo composite on the same panel
  * a zero-cost control on the frozen variant, to separate cost drag from edge
"""

from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
from harness import (
    COST_MODEL,
    HERE,
    RT_BPS,
    TEST_END,
    TEST_START,
    ZERO_COST,
    ZERO_RT_BPS,
    build_score,
    buy_and_hold,
    composite,
    fmt,
    load_panel,
    random_control,
    run,
    signal_panel,
    summarise,
)

OUT: dict = {}


def main() -> None:
    with open(os.path.join(HERE, "selected.json")) as f:
        sel = json.load(f)
    period, ranker, vname = sel["period"], sel["rank"], sel["variant"]
    print(f"FROZEN VARIANT (from selected.json, TRAIN-selected): {vname} "
          f"period={period} ranker={ranker}")
    print(f"TEST window: {TEST_START.date()} -> {TEST_END.date()}")
    print(f"cost: {RT_BPS:.2f} bps round trip   (zero-cost control {ZERO_RT_BPS:.2f} bps)\n")

    panel_full = load_panel()

    # Indicators on full history; prices sliced to TEST for the backtest. Mirrors the
    # TRAIN construction exactly so the two are comparable.
    te = panel_full.loc[:TEST_END].loc[TEST_START:]
    score = build_score(panel_full, period, ranker).loc[:TEST_END].loc[TEST_START:]

    print(f"TEST panel: {te.shape[0]} bars x {te.shape[1]} symbols")
    holes = te.isna().sum()
    holes = holes[holes > 0]
    print(f"TEST panel interior holes: {dict(holes.astype(int)) if len(holes) else 'none'}")
    for c in holes.index:
        idx = te.index[te[c].isna()]
        print(f"  {c}: {len(idx)} bar(s) -> {[str(d.date()) for d in idx]}")
    print("  (these are raw-file gaps, NOT loader output: verified against the CSV. "
          "run_backtest earns 0% for the name that day and never holds it.")
    OUT["window"] = {
        "test": [str(TEST_START.date()), str(TEST_END.date())],
        "bars": int(len(te)),
        "symbols": int(te.shape[1]),
    }
    OUT["selected"] = sel

    # ---- the strategy -----------------------------------------------------
    res = run(te, score, COST_MODEL)
    strat = summarise(res, "TEMA V4 (net 21.92bps)")
    strat["variant"] = vname
    strat["period"] = period
    strat["rank"] = ranker
    print("\nTEST RESULT")
    print("  " + fmt(strat))

    # ---- zero-cost control on the same frozen variant ---------------------
    res0 = run(te, score, ZERO_COST)
    strat0 = summarise(res0, "TEMA V4 (ZERO cost 11.92bps)")
    strat0["variant"] = vname
    strat0["zero_cost"] = True
    print("  " + fmt(strat0))

    # ---- buy and hold -----------------------------------------------------
    bh = buy_and_hold(te, COST_MODEL)
    print("  " + fmt(bh))
    print(f"    gross (no cost): CAGR {bh['cagr_gross'] * 100:.2f}%  "
          f"MaxDD {bh['max_drawdown_gross'] * 100:.2f}%  "
          f"cost drag {bh['cost_drag_annual'] * 100:.2f}%/y")

    # ---- nsealgo composite ------------------------------------------------
    comp = composite(panel_full, COST_MODEL, start=TEST_START, end=TEST_END)
    print("  " + fmt(comp))

    # ---- random-signal control -------------------------------------------
    print("\nRANDOM-SIGNAL CONTROL (same long-fraction, 10 seeds)")
    sig = signal_panel(panel_full, period).loc[:TEST_END].loc[TEST_START:]
    long_frac = float((sig > 0).sum().sum() / sig.notna().sum().sum())
    print(f"  real gate long-fraction on TEST: {long_frac * 100:.1f}%")
    rands = []
    for seed in range(10):
        r = random_control(panel_full, period, ranker, 1.0, seed, COST_MODEL,
                           long_frac=long_frac, start=TEST_START, end=TEST_END)
        rands.append(r)
    print("  " + fmt(rands[0]).replace(rands[0]["label"], "random (seed 0)"))
    for r in rands:
        print(f"    seed {r['label'].split('seed')[-1]:>2}: CAGR {r['cagr'] * 100:>7.2f}%  "
              f"Sharpe {r['sharpe']:>6.2f}  MaxDD {r['max_drawdown'] * 100:>7.2f}%"
              f"  names {r['avg_names']:>5.1f}")

    # ---- sanity: weight count, equity curve -------------------------------
    w = res.weights
    names = (w > 0).sum(axis=1)
    print(f"\nSANITY  avg names held {names.mean():.2f}  max {names.max()}  "
          f"min {names.min()}  (cap is {w.shape[1]} columns; target 22)")
    print(f"        max single weight {w.max().max():.4f} (cap 0.12)")
    print(f"        final equity {res.equity.iloc[-1]:.4f}  -> CAGR "
          f"{res.metrics.cagr * 100:.2f}% (a >50% CAGR would indicate a bug)")

    # ---- yearly returns ---------------------------------------------------
    yb = pd.DataFrame({
        "strategy": res.returns,
        "buy_and_hold": bh["equity_net"].pct_change(fill_method=None).fillna(0.0),
        "composite": comp["returns"],
    }).loc[TEST_START:TEST_END]
    yr = yb.resample("YE").apply(lambda s: (1 + s).prod() - 1)
    yr.index = yr.index.year
    yr.loc["ALL (CAGR)"] = [
        res.metrics.cagr,
        bh["equity_net"].iloc[-1] ** (244 / len(te)) - 1,
        comp["cagr"],
    ]
    print("\nYEARLY RETURNS (net)")
    print(yr.to_string(float_format=lambda x: f"{x * 100:>7.2f}%"))
    print(f"\n  positive years: strategy "
          f"{int((yr.iloc[:-1].strategy > 0).sum())}/{len(yr) - 1}   "
          f"B&H {int((yr.iloc[:-1].buy_and_hold > 0).sum())}/{len(yr) - 1}   "
          f"composite {int((yr.iloc[:-1].composite > 0).sum())}/{len(yr) - 1}")

    OUT["strategy"] = strat
    OUT["strategy_zero_cost"] = strat0
    OUT["buy_and_hold"] = {k: v for k, v in bh.items() if k not in ("equity_net", "equity_gross")}
    OUT["composite"] = {k: v for k, v in comp.items() if k not in ("equity", "returns")}
    OUT["random"] = rands
    OUT["random_summary"] = {
        "n_seeds": len(rands),
        "cagr_mean": float(np.mean([r["cagr"] for r in rands])),
        "cagr_std": float(np.std([r["cagr"] for r in rands])),
        "cagr_max": float(np.max([r["cagr"] for r in rands])),
        "sharpe_mean": float(np.mean([r["sharpe"] for r in rands])),
        "sharpe_max": float(np.max([r["sharpe"] for r in rands])),
        "maxdd_worst": float(np.min([r["max_drawdown"] for r in rands])),
        "real_long_frac": long_frac,
    }
    OUT["sanity"] = {
        "avg_names": float(names.mean()),
        "max_names": int(names.max()),
        "min_names": int(names.min()),
        "max_single_weight": float(w.max().max()),
        "final_equity": float(res.equity.iloc[-1]),
    }
    OUT["yearly"] = yr.to_dict()

    # equity curves for the plot-free report
    eq = pd.DataFrame({
        "strategy": res.equity,
        "strategy_zero_cost": res0.equity,
        "buy_and_hold": bh["equity_net"].reindex(res.equity.index),
        "composite": comp["equity"].reindex(res.equity.index),
        "random_seed0": None,
    }).dropna(how="all")
    eq.to_csv(os.path.join(HERE, "test_equity.csv"))
    OUT["random_summary"]["beat_rate"] = float(
        np.mean([strat["sharpe"] > r["sharpe"] for r in rands])
    )
    OUT["random_summary"]["beat_rate_cagr"] = float(
        np.mean([strat["cagr"] > r["cagr"] for r in rands])
    )

    with open(os.path.join(HERE, "test_results.json"), "w") as f:
        json.dump(OUT, f, indent=2, default=str)
    print("\nwrote test_results.json + test_equity.csv")


if __name__ == "__main__":
    main()
