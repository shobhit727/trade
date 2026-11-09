"""THE SINGLE TEST READ. Run exactly once. Nothing is re-tuned after seeing output.

Protocol (brief section 4):
  * V4 was selected on TRAIN and frozen to selected_variant.json.
  * This script asserts the engine has not moved since selection.
  * It then evaluates, on TEST only: the strategy, buy-and-hold, the composite,
    a random-signal control, a signal-scrambled control, and a zero-cost run.

All headline numbers net of 21.92 bps (engine `all_in_round_trip_bps`).
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from common import (
    COSTS_ZERO,
    ENGINE_SHA,
    HDR,
    avg_names,
    buy_and_hold,
    fmt_yearly,
    full_panel,
    invested_frac,
    row,
    run,
    test_slice,
    tmr_score,
)

from nsealgo.backtest.metrics import yearly_returns
from nsealgo.factors.core import build_composite_score

sel = json.load(open("selected_variant.json"))
assert sel["engine_sha"] == ENGINE_SHA, (
    f"ENGINE MOVED: selected under {sel['engine_sha']}, now {ENGINE_SHA}"
)
print("engine MATCH — selection is valid\n")
print(f"TEST evaluation of TRAIN-selected {sel['variant']} "
      f"(slow={sel['slow']}, entry={sel['entry']}, mom={sel['mom_days']}d, "
      f"z={sel['z_window']})")
print("Window: 2024-01-01 -> 2026-10-01. This is the one and only TEST read.\n")

SLOW, ENTRY = sel["slow"], sel["entry"]
panel = full_panel()
te_panel = test_slice(panel)
score = test_slice(tmr_score(panel, SLOW, ENTRY))

# --------------------------------------------------------------------------- #
# 1. The strategy
# --------------------------------------------------------------------------- #
real = run(te_panel, score, label="TEST real")
print(HDR)
print(row("TEST strategy (V4)", real.metrics,
          f"names {avg_names(real):.1f}, inv {invested_frac(real) * 100:.0f}%"))
print(f"  yearly: {fmt_yearly(yearly_returns(real.returns))}")

# --------------------------------------------------------------------------- #
# 2. Buy-and-hold, identical window, same costs
# --------------------------------------------------------------------------- #
bh = buy_and_hold(te_panel, "TEST buy_and_hold")
print(row("TEST buy-and-hold", bh["metrics"],
          f"net {bh['round_trip_bps']:.2f}bps, nan_frac {bh['nan_frac']:.3f}"))
print(f"  yearly: {fmt_yearly(bh['yearly'])}")

# --------------------------------------------------------------------------- #
# 3. Zero-cost control (11.92 bps statutory only)
# --------------------------------------------------------------------------- #
real_zero = run(te_panel, score, costs=COSTS_ZERO, label="TEST zero cost")
print(row("TEST strategy @ 0 slippage", real_zero.metrics, "11.92bps A/B"))

# --------------------------------------------------------------------------- #
# 4. nsealgo composite benchmark
# --------------------------------------------------------------------------- #
comp_res = run(te_panel, build_composite_score(te_panel), label="TEST composite")
print(row("TEST nsealgo composite", comp_res.metrics,
          f"names {avg_names(comp_res):.1f}"))
print(f"  yearly: {fmt_yearly(yearly_returns(comp_res.returns))}")

# --------------------------------------------------------------------------- #
# 5. Random-signal control, same live fraction, 20 seeds
# --------------------------------------------------------------------------- #
n_flagged = score.notna().sum(axis=1)
print(f"\n--- controls (live fraction {score.notna().to_numpy().sum() / score.notna().size * 100:.2f}%) ---")
rand = []
for seed in range(20):
    rng = np.random.default_rng(20261011 + seed)
    arr = np.full(score.shape, np.nan)
    for i in range(len(score)):
        k = int(n_flagged.iloc[i])
        if k == 0:
            continue
        cols = rng.choice(arr.shape[1], size=k, replace=False)
        arr[i, cols] = rng.permutation(np.arange(1, k + 1) / k)
    r = run(te_panel, pd.DataFrame(arr, index=score.index, columns=score.columns),
            label=f"rand{seed}")
    rand.append({"seed": seed, "cagr": float(r.metrics.cagr),
                 "sharpe": float(r.metrics.sharpe),
                 "max_drawdown": float(r.metrics.max_drawdown)})

rc = np.array([x["cagr"] for x in rand])
rs = np.array([x["sharpe"] for x in rand])
print(f"RANDOM    : CAGR {rc.mean() * 100:6.2f}% mean  "
      f"[p10 {np.percentile(rc, 10) * 100:6.2f}%, p90 {np.percentile(rc, 90) * 100:6.2f}%]  "
      f"Sharpe {rs.mean():.2f}  -> real CAGR percentile "
      f"{(rc < real.metrics.cagr).mean() * 100:.0f}th, "
      f"Sharpe {(rs < real.metrics.sharpe).mean() * 100:.0f}th")

# --------------------------------------------------------------------------- #
# 6. Signal-scrambled control: permute score across symbols within each date
# --------------------------------------------------------------------------- #
scr = []
for seed in range(20):
    rng = np.random.default_rng(777000 + seed)
    arr = score.to_numpy().copy()
    for i in range(arr.shape[0]):
        rv = arr[i]
        v = ~np.isnan(rv)
        if v.sum() > 1:
            vals = rv[v].copy()
            rng.shuffle(vals)
            rv[v] = vals
            arr[i] = rv
    r = run(te_panel, pd.DataFrame(arr, index=score.index, columns=score.columns),
            label=f"scr{seed}")
    scr.append({"seed": seed, "cagr": float(r.metrics.cagr),
                "sharpe": float(r.metrics.sharpe),
                "max_drawdown": float(r.metrics.max_drawdown)})

sc = np.array([x["cagr"] for x in scr])
ss = np.array([x["sharpe"] for x in scr])
print(f"SCRAMBLED : CAGR {sc.mean() * 100:6.2f}% mean  "
      f"[p10 {np.percentile(sc, 10) * 100:6.2f}%, p90 {np.percentile(sc, 90) * 100:6.2f}%]  "
      f"Sharpe {ss.mean():.2f}  -> real CAGR percentile "
      f"{(sc < real.metrics.cagr).mean() * 100:.0f}th, "
      f"Sharpe {(ss < real.metrics.sharpe).mean() * 100:.0f}th")

# --------------------------------------------------------------------------- #
# 7. Verdict arithmetic
# --------------------------------------------------------------------------- #
print("\n" + "=" * 78)
print("VERDICT ARITHMETIC (TEST, net of 21.92 bps)")
print("=" * 78)
print(f"strategy CAGR   {real.metrics.cagr * 100:6.2f}%  Sharpe {real.metrics.sharpe:+.2f}  "
      f"MaxDD {real.metrics.max_drawdown * 100:6.2f}%")
print(f"buy&hold CAGR   {bh['metrics'].cagr * 100:6.2f}%  Sharpe {bh['metrics'].sharpe:+.2f}  "
      f"MaxDD {bh['metrics'].max_drawdown * 100:6.2f}%")
print(f"composite CAGR  {comp_res.metrics.cagr * 100:6.2f}%  Sharpe {comp_res.metrics.sharpe:+.2f}  "
      f"MaxDD {comp_res.metrics.max_drawdown * 100:6.2f}%")
print(f"random  CAGR    {rc.mean() * 100:6.2f}% (mean)")
print(f"scramble CAGR   {sc.mean() * 100:6.2f}% (mean)")
print()
print(f"vs buy&hold : {(real.metrics.cagr - bh['metrics'].cagr) * 100:+.2f} pts/yr return, "
      f"{(real.metrics.max_drawdown - bh['metrics'].max_drawdown) * 100:+.2f} pts drawdown")
print(f"vs composite: {(real.metrics.cagr - comp_res.metrics.cagr) * 100:+.2f} pts/yr return, "
      f"{(real.metrics.max_drawdown - comp_res.metrics.max_drawdown) * 100:+.2f} pts drawdown")
print(f"vs scramble : {(real.metrics.cagr - sc.mean()) * 100:+.2f} pts/yr return, "
      f"Sharpe {real.metrics.sharpe - ss.mean():+.2f}")
print(f"vs random   : {(real.metrics.cagr - rc.mean()) * 100:+.2f} pts/yr return, "
      f"Sharpe {real.metrics.sharpe - rs.mean():+.2f}")

out = {
    "variant": sel["variant"],
    "slow": SLOW,
    "entry": ENTRY,
    "window": ["2024-01-01", "2026-10-01"],
    "engine_sha": real.engine_sha,
    "strategy": {
        "cagr": float(real.metrics.cagr), "sharpe": float(real.metrics.sharpe),
        "calmar": float(real.metrics.calmar),
        "max_drawdown": float(real.metrics.max_drawdown),
        "total_return": float(real.metrics.total_return),
        "volatility": float(real.metrics.volatility),
        "annual_turnover": float(real.metrics.annual_turnover),
        "cost_drag_annual": float(real.metrics.cost_drag_annual),
        "avg_names": avg_names(real), "invested": invested_frac(real),
        "yearly": {str(k): float(v) for k, v in yearly_returns(real.returns).items()},
    },
    "buy_and_hold": {
        "cagr": float(bh["metrics"].cagr), "sharpe": float(bh["metrics"].sharpe),
        "calmar": float(bh["metrics"].calmar),
        "max_drawdown": float(bh["metrics"].max_drawdown),
        "total_return": float(bh["metrics"].total_return),
        "yearly": {str(k): float(v) for k, v in bh["yearly"].items()},
    },
    "composite": {
        "cagr": float(comp_res.metrics.cagr), "sharpe": float(comp_res.metrics.sharpe),
        "max_drawdown": float(comp_res.metrics.max_drawdown),
    },
    "zero_cost": {
        "cagr": float(real_zero.metrics.cagr), "sharpe": float(real_zero.metrics.sharpe),
        "max_drawdown": float(real_zero.metrics.max_drawdown),
        "cost_drag_annual": float(real_zero.metrics.cost_drag_annual),
    },
    "random": {
        "seeds": rand, "cagr_mean": float(rc.mean()), "sharpe_mean": float(rs.mean()),
        "cagr_p10": float(np.percentile(rc, 10)), "cagr_p90": float(np.percentile(rc, 90)),
        "real_cagr_percentile": float((rc < real.metrics.cagr).mean()),
        "real_sharpe_percentile": float((rs < real.metrics.sharpe).mean()),
    },
    "scrambled": {
        "seeds": scr, "cagr_mean": float(sc.mean()), "sharpe_mean": float(ss.mean()),
        "cagr_p10": float(np.percentile(sc, 10)), "cagr_p90": float(np.percentile(sc, 90)),
        "real_cagr_percentile": float((sc < real.metrics.cagr).mean()),
        "real_sharpe_percentile": float((ss < real.metrics.sharpe).mean()),
    },
}
with open("test_results.json", "w") as fh:
    json.dump(out, fh, indent=2)
print("\nwrote test_results.json")
