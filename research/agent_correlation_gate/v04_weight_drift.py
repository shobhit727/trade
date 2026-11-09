"""Is avg names=28.84 (target 22, cap 30) a bug or legitimate drift?

Hypothesis: turnover_budget=0.35 means at most 35% of the book may change per
monthly rebalance. Exits therefore cannot be fully replaced each rebalance, so the
book drifts up toward max_names=30 and plateaus. That would be legitimate (and is
the documented cost of the turnover budget), whereas a *monotonically* growing count
would be residual-weight accumulation.

Also checks constraint compliance directly.
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "src")
sys.path.insert(0, "research/agent_correlation_gate")

from common import PCFG, TEST_END, TRAIN_START, backtest, load, score_from_signal, signal_panel  # noqa: E402

panel, _, _ = load()
res = backtest(panel, score_from_signal(signal_panel(panel, 10, 0.01), panel, 10),
               TRAIN_START, TEST_END)
w = res.weights
nc = (w > 0).sum(axis=1)
gross = w.sum(axis=1)

print(f"rebalances: {len(nc)}  turnover_budget={PCFG.turnover_budget}")
print("\nnames held, by year (does it PLATEAU or grow without bound?)")
by = nc.groupby(nc.index.year).agg(["mean", "min", "max", "count"])
print(by.round(2).to_string())

first, last = nc.iloc[:12].mean(), nc.iloc[-12:].mean()
print(f"\n  first 12 rebalances avg names : {first:.2f}")
print(f"  last  12 rebalances avg names : {last:.2f}")
print(f"  drift {last - first:+.2f} names over the window")

print("\n  first 16 rebalance dates / names / gross (looking for a cash-only warmup)")
for d, n, g in list(zip(nc.index, nc.to_numpy(), gross.to_numpy(), strict=True))[:16]:
    print(f"    {str(d.date())}  names={n:3d}  gross={g * 100:6.2f}%")

# how often is the book saturated at max_names vs near the n_positions target?
print(f"\n  rebalances at max_names={PCFG.max_names}: "
      f"{int((nc == PCFG.max_names).sum())}/{len(nc)}")
print(f"  rebalances within +-2 of n_positions={PCFG.n_positions}: "
      f"{int(((nc - PCFG.n_positions).abs() <= 2).sum())}/{len(nc)}")

# monotone growth test: fit a line to the count and report slope per rebalance
x = np.arange(len(nc), dtype=float)
slope = np.polyfit(x, nc.to_numpy(dtype=float), 1)[0]
print(f"  OLS slope of names vs rebalance index: {slope * 100:+.4f} names per 100 rebalances")
print(f"  -> {'PLATEAUS (turnover-budget drift, legitimate)' if abs(slope) < 0.01 else 'GROWS (suspect accumulation)'}")

# dead-weight tail: what fraction of the book sits in positions below DEAD_WEIGHT_EPS?
tiny = (w > 0) & (w < 1e-3)
print(f"\npositions held but < 0.1% of book: {int(tiny.sum().sum())} cells "
      f"({100 * tiny.sum().sum() / max(1, (w > 0).sum().sum()):.2f}% of held positions)")
print(f"their total weight: {w.where(tiny).sum(axis=1).mean() * 100:.3f}% of book "
      f"(i.e. dust, not drift)")

print("\nconstraint compliance across every rebalance")
gross = w.sum(axis=1)
checks = {
    f"single weight <= {PCFG.max_weight:.0%}": (w.max(axis=1) <= PCFG.max_weight + 1e-9).all(),
    f"cash >= {PCFG.cash_buffer:.0%} (gross <= {1 - PCFG.cash_buffer:.0%})":
        (gross <= 1 - PCFG.cash_buffer + 1e-9).all(),
    f"names <= max_names ({PCFG.max_names})": (nc <= PCFG.max_names).all(),
    "weights >= 0": bool((w.to_numpy() >= -1e-12).all()),
    "no NaN in weights": bool(np.isfinite(w.to_numpy()).all()),
}
for k, ok in checks.items():
    print(f"  {'PASS' if ok else 'FAIL'}  {k}")
print(f"\n  max observed gross exposure {gross.max() * 100:.2f}%   "
      f"min cash {(1 - gross.max()) * 100:.2f}%")
