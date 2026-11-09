"""Step 02 — TRAIN-ONLY: run the 5 declared variants, select one.

This script CANNOT see TEST: the panel is truncated at 2023-12-31 before anything is
built. Selection rule is declared in DECLARED_BUDGET.md: highest TRAIN Sharpe,
tie-break lower TRAIN cost drag.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "research/agent_bollinger_bands")
sys.path.insert(0, "src")

import json

import numpy as np
import pandas as pd
from common import PORT, TRAIN, bh_panel, bollinger_position, fmt, gate, load_panel, make_score, run

from nsealgo.backtest.engine import run_backtest
from nsealgo.costs import CostModel
from nsealgo.factors.core import build_composite_score

ZERO = CostModel(segment="delivery", slippage_bps=0)

panel_full = load_panel()
panel = panel_full.loc[: TRAIN[1]].copy()  # TEST physically absent from this process
assert panel.index.max() <= pd.Timestamp(TRAIN[1], tz=panel.index.tz)

VARIANTS = [
    ("V1 bb_pure_default", 20, 2.0, 1.0, "pure"),
    ("V2 bb_hybrid_mom6m", 20, 2.0, 1.0, "hybrid"),
    ("V3 bb_pure_deep", 20, 2.5, 1.0, "pure"),
    ("V4 bb_pure_slow", 60, 2.0, 1.0, "pure"),
    ("V5 bb_pure_fast", 10, 2.0, 1.0, "pure"),
]


def random_control(panel, period, n_std, entry, seed):
    """Random signal selecting the SAME number of names per day as the real signal."""
    g = gate(bollinger_position(panel, period, n_std), entry)
    rng = np.random.default_rng(seed)
    counts = g.sum(axis=1).to_numpy()
    cols = panel.shape[1]
    s = np.full(g.shape, np.nan)
    for i in range(g.shape[0]):
        k = int(counts[i])
        if k:
            pick = rng.choice(cols, size=min(k, cols), replace=False)
            s[i, pick] = rng.permutation(len(pick)).astype(float)
    return pd.DataFrame(s, index=panel.index, columns=panel.columns)


def show(label, res):
    print(fmt(label, res.metrics,
              {"avg_names": round(res.diag["avg_names"], 1),
               "nrb": res.diag["n_rebalances"]}))


print("=" * 104)
print(f"TRAIN-ONLY  {panel.index.min().date()} -> {panel.index.max().date()}  "
      f"({len(panel)} bars, {panel.shape[1]} symbols)")
print("=" * 104)
print("-" * 104)
print("DECLARED VARIANTS (5) — net of the full Indian delivery stack")
print("-" * 104)

results = {}
for name, period, n_std, entry, constr in VARIANTS:
    score = make_score(panel, period, n_std, entry, constr)
    res = run(panel, score)
    results[name] = (period, n_std, entry, constr, res)
    show(name, res)

print("-" * 104)
print("BASELINES (reported, never selected)")
print("-" * 104)
base = {}
for nm, sc in (("BASE buy-and-hold", bh_panel(panel)),
               ("BASE nsealgo composite", build_composite_score(panel))):
    base[nm] = run(panel, sc)
    show(nm, base[nm])

print("-" * 104)
print("NEGATIVE CONTROL — random signal, identical per-day name count, 5 seeds")
print("-" * 104)
rand = []
for s in range(5):
    sc = random_control(panel, 20, 2.0, 1.0, seed=20260101 + 1000 * s)
    r = run(panel, sc)
    rand.append(r)
    show(f"CTRL random seed{s}", r)
print(f"  CTRL mean  : CAGR {np.mean([r.metrics.cagr for r in rand])*100:>6.2f}%  "
      f"Sharpe {np.mean([r.metrics.sharpe for r in rand]):>5.2f}  "
      f"MaxDD {np.mean([r.metrics.max_drawdown for r in rand])*100:>6.2f}%  "
      f"avgNames {np.mean([r.diag['avg_names'] for r in rand]):.1f}")

print()
print("-" * 104)
print("COST DRAG DECOMPOSITION (same holdings, full stack vs zero-slippage)")
print("-" * 104)
for name, period, n_std, entry, constr in VARIANTS:
    score = make_score(panel, period, n_std, entry, constr)
    net = results[name][4]
    z = run_backtest(panel, score, ZERO, PORT, rebalance="M")
    print(f"  {name:<22} net CAGR {net.metrics.cagr*100:>7.2f}%   "
          f"zero-cost CAGR {z.metrics.cagr*100:>7.2f}%   "
          f"drag {(net.metrics.cagr-z.metrics.cagr)*100:>6.2f} pp/y   "
          f"turnover {net.metrics.annual_turnover:.2f}x/y")

# ------------------------------------------------------------------ selection
print()
print("=" * 104)
best_name = max(results, key=lambda k: (round(results[k][4].metrics.sharpe, 6),
                                        -results[k][4].metrics.cost_drag_annual))
p, n, e, c, res = results[best_name]
print(f"SELECTED ON TRAIN (rule: max TRAIN Sharpe): {best_name}   "
      f"Sharpe {res.metrics.sharpe:.3f}  CAGR {res.metrics.cagr*100:.2f}%")
print("=" * 104)

with open("research/agent_bollinger_bands/selected_variant.json", "w") as fh:
    json.dump({"label": best_name, "period": p, "n_std": n, "entry": e,
               "construction": c,
               "train_sharpe": float(res.metrics.sharpe),
               "train_cagr": float(res.metrics.cagr),
               "train_maxdd": float(res.metrics.max_drawdown),
               "budget_used": len(VARIANTS),
               "budget_allowed": 5}, fh, indent=2)
print(open("research/agent_bollinger_bands/selected_variant.json").read())
