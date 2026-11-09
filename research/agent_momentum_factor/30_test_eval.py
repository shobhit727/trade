"""30 — THE single TEST evaluation of the TRAIN-frozen variant, plus all controls.

M4 was selected on TRAIN by the rule declared before any run. It is evaluated here
unchanged on TEST 2024-01-01 -> 2026-10-01, net of the engine's 21.92 bps all-in rate.

Also evaluated on TEST, for comparison only (NOT candidates, nothing is selected here):
  * buy-and-hold, identical window, same costs
  * the nsealgo composite on the same panel
  * a random-signal control matched on eligible-name count, 5 seeds
  * all 5 variants vs the benchmark (reported so the TRAIN ranking is visible OOS)
"""

from __future__ import annotations

import json
from decimal import Decimal as _D

import common
import numpy as np

from nsealgo.backtest.engine import PortfolioConfig, run_backtest
from nsealgo.costs import CostModel as CM

SELECTED = "M4"
S, E = common.TEST_START, common.TEST_END

panel, symbols, _ = common.load_panel()
v = common.BY_TAG[SELECTED]

print(f"TEST window: {S.date()} -> {E.date()}   selected on TRAIN: {SELECTED} "
      f"(period {v.period}, thr {v.threshold}, rank {v.rank_days}, reb {v.rebalance})")

score = common.build_score(panel, v)
res = common.run(panel, score, v, S, E)
m = res.metrics

# ---- the headline row
strat = common.metrics_row("STRATEGY " + SELECTED, m)
strat["avg_names"] = res.diag["avg_names"]
strat["max_single_w"] = float(res.weights.max().max())
strat["invested"] = float(res.weights.sum(axis=1).mean())

# ---- buy-and-hold, same window, same cost stack
bh_d, bh_eq, bh_m, bh_names = common.benchmark_buy_hold(panel, S, E)
bh = common.metrics_row("BUY-AND-HOLD", bh_m)
bh["avg_names"] = bh_names

# ---- nsealgo house composite on the same panel
comp_score = common.composite_score(panel)
comp = common.run(panel, comp_score, v, S, E)
comp_row = common.metrics_row("NSEALGO COMPOSITE", comp.metrics)
comp_row["avg_names"] = comp.diag["avg_names"]

# ---- random-signal control, 5 seeds, matched on eligible-name count
rand_rows = []
for seed in (1, 2, 3, 4, 5):
    rr = common.random_control(panel, v, S, E, seed)
    r = common.metrics_row(f"rand{seed}", rr.metrics)
    r["avg_names"] = rr.diag["avg_names"]
    rand_rows.append(r)
    print(f"  rand seed {seed}: CAGR {rr.metrics.cagr * 100:6.2f}%  "
          f"Sharpe {rr.metrics.sharpe:5.2f}  MaxDD {rr.metrics.max_drawdown * 100:7.2f}%  "
          f"avg names {rr.diag['avg_names']:.1f}")

# ---- every declared variant on TEST (reporting only; M4 remains the frozen pick)
all_v = []
for vv in common.VARIANTS:
    rr = common.run(panel, common.build_score(panel, vv), vv, S, E)
    row = common.metrics_row(vv.tag, rr.metrics)
    row["avg_names"] = rr.diag["avg_names"]
    row["selected"] = "<< TRAIN pick" if vv.tag == SELECTED else ""
    all_v.append(row)

# ---- liveness on TEST for the selected variant
sig = common.strategy_signal(panel, v.period, v.threshold)
tw = sig.loc[(sig.index >= S) & (sig.index <= E)]
cells = tw.to_numpy().ravel()
liveness = {
    "long_frac": float((cells > 0).mean()),
    "flat_frac": float((cells == 0).mean()),
    "short_frac": float((cells < 0).mean()),
    "avg_eligible_per_day": float((tw > 0).sum(axis=1).mean()),
}

# ---- zero-cost counterfactual: is the failure cost-driven? (diagnostic, not a result)
# NOTE: `slippage_bps` must be a Decimal/int here — a float raises TypeError inside
# `all_in_round_trip_bps` (BUG-1 in BUGS.md). Decimal("0") is the workaround.
gross_cost = CM(segment="delivery", slippage_bps=_D("0"))
double_cost = CM(segment="delivery", slippage_bps=_D("10"))

g_idx = panel.index[(panel.index >= S) & (panel.index <= E)]
g_res = run_backtest(panel.loc[g_idx], score.reindex(g_idx), gross_cost,
                     PortfolioConfig(), rebalance=v.rebalance)
d_res = run_backtest(panel.loc[g_idx], score.reindex(g_idx), double_cost,
                     PortfolioConfig(), rebalance=v.rebalance)
zero_cost = {"cagr": g_res.metrics.cagr, "sharpe": g_res.metrics.sharpe,
             "maxdd": g_res.metrics.max_drawdown}
double_cost_m = {"cagr": d_res.metrics.cagr, "sharpe": d_res.metrics.sharpe,
                 "maxdd": d_res.metrics.max_drawdown}

# ---- yearly
import pandas as pd  # noqa: E402

yr_s = common.yearly_returns(res.returns)
yr_b = common.yearly_returns(bh_d)
yr = {"year": [str(y) for y in yr_s.index],
      "strategy": yr_s.tolist(), "bh": yr_b.reindex(yr_s.index).tolist()}

print()
print("=== TEST, net of 21.92 bps all-in ===")
print(common.fmt_table([strat, bh, comp_row],
                       ["tag", "cagr", "sharpe", "sortino", "maxdd", "calmar", "vol",
                        "total", "turnover", "cost_drag", "trades", "winrate",
                        "avg_names"]))
print()
print("cost charged (Rs, on the Rs 21,00,000 book):", f"{res.costs_paid:,.0f}")
print("max single weight:", f"{strat['max_single_w'] * 100:.2f}%", "(cap 12%)")
print("mean invested     :", f"{strat['invested'] * 100:.1f}%", "(target 90%)")
print("liveness on TEST  :", {k: round(v_, 4) for k, v_ in liveness.items()})
print("zero-cost CAGR %  :", f"{zero_cost['cagr'] * 100:.2f}",
      " Sharpe", round(zero_cost["sharpe"], 3))
print()
print("yearly returns:")
print(pd.DataFrame(yr).to_string(index=False))
print()
print("all 5 variants on TEST (reporting only):")
print(common.fmt_table(all_v, ["tag", "cagr", "sharpe", "maxdd", "turnover",
                               "cost_drag", "avg_names", "selected"]))
print()
print("random control mean CAGR %:",
      round(float(np.mean([r["cagr"] for r in rand_rows])) * 100, 2),
      " Sharpe", round(float(np.mean([r["sharpe"] for r in rand_rows])), 3),
      " MaxDD %", round(float(np.mean([r["maxdd"] for r in rand_rows])) * 100, 2))

res.equity.to_csv(f"{common.OUT_DIR}/test_equity_{SELECTED}.csv")
bh_eq.to_csv(f"{common.OUT_DIR}/test_equity_bh.csv")

payload = {
    "selected": SELECTED,
    "window": [str(S.date()), str(E.date())],
    "strategy": strat, "buy_and_hold": bh, "composite": comp_row,
    "random_seeds": rand_rows,
    "all_variants_test": all_v,
    "liveness_test": liveness,
    "zero_cost": zero_cost,
    "yearly": yr,
    "costs_paid_rs": res.costs_paid,
}
with open(f"{common.OUT_DIR}/30_test.json", "w") as f:
    json.dump(payload, f, indent=2)
print(f"\nwrote {common.OUT_DIR}/30_test.json")
