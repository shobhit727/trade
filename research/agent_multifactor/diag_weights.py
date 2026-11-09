"""Diagnostic: does `run_backtest` keep the book at its configured investment level?

`PortfolioConfig(cash_buffer=0.10)` implies the book should hold ~0.90 of equity
at all times, and `build_rebalance_weights` explicitly emits a target summing to
0.90 (`w_full *= (1 - cash_buffer)`).

This script measures what the book ACTUALLY holds, and attributes any shortfall.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "research/agent_multifactor")

import pandas as pd  # noqa: E402
from harness import CM, PANEL, PortfolioConfig, run_backtest, score_variant  # noqa: E402

from nsealgo.backtest.engine import build_rebalance_weights  # noqa: E402

cfg = PortfolioConfig()
sc = score_variant(PANEL, 20, 14, 126, False)
res = run_backtest(PANEL, sc, CM, cfg, rebalance="M")

w = res.weights
total = w.sum(axis=1)
names = (w > 0).sum(axis=1)

print("held book (full history)")
print(f"  invested fraction : mean {total.mean():.4f}  min {total.min():.4f}  "
      f"max {total.max():.4f}")
print(f"  names held        : mean {names.mean():.1f}  min {names.min()}  "
      f"max {names.max()}")
print(f"  implied cash      : mean {1 - total.mean():.4f}  (config asks for 0.10)")

# Target weights, before the turnover budget is applied.
idx = PANEL.index.intersection(sc.index)
px = PANEL.loc[idx]
vol = px.pct_change(fill_method=None).fillna(0.0).rolling(
    cfg.vol_lookback, min_periods=20
).std()
from nsealgo.backtest.engine import _rebalance_dates  # noqa: E402

rb = [d for d in _rebalance_dates(px.index, "M") if d in sc.index][1:]
tgt = build_rebalance_weights(sc.loc[rb], rb, vol.loc[rb], cfg)
tgt_total = tgt.sum(axis=1)
print("\nTARGET weights (as built by build_rebalance_weights, pre-budget)")
print(f"  invested fraction : mean {tgt_total.mean():.4f}  "
      f"min {tgt_total.min():.4f}  max {tgt_total.max():.4f}")

# One-way turnover actually demanded at each rebalance, vs the 0.35 budget.
demanded = (tgt - tgt.shift(1).fillna(0.0)).abs().sum(axis=1) / 2.0
print("\none-way turnover DEMANDED per rebalance vs budget")
print(f"  mean {demanded.mean():.4f}  p50 {demanded.median():.4f}  "
      f"p90 {demanded.quantile(0.9):.4f}  max {demanded.max():.4f}  "
      f"budget {cfg.turnover_budget}")
print(f"  rebalances where demand > budget: "
      f"{(demanded > cfg.turnover_budget).mean() * 100:.1f}%")
lam = (cfg.turnover_budget / demanded).clip(upper=1.0)
print(f"  implied lam: mean {lam.mean():.3f}  p10 {lam.quantile(0.1):.3f}  "
      f"p50 {lam.median():.3f}")

# How long does a full rotation actually take?
cum = lam.cumsum()
print(f"  rebalances needed to complete one full 100% rotation: ~{1 / lam.mean():.1f}"
      f" months (at the mean lam)")

print("\nweight distribution on a sample of rebalance dates")
for d in rb[:: max(len(rb) // 8, 1)]:
    row = w.loc[d]
    live = row[row > 0].sort_values(ascending=False)
    print(f"  {pd.Timestamp(d).date()}  invested {row.sum():.3f}  "
          f"names {len(live):>2}  largest {live.iloc[0] if len(live) else 0:.4f}")
