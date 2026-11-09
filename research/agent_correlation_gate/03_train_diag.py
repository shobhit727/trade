"""TRAIN-only structural diagnostics for the champion (V2: period=10, thr=0.01).

Checks the brief's section-6 sanity list that can be answered without TEST:
plausibility, weight count, signal liveness, cost drag (gross vs net).
"""
from decimal import Decimal

from common import (
                    PCFG,
                    TRAIN_END,
                    TRAIN_START,
                    backtest,
                    live_frac,
                    load,
                    score_from_signal,
                    signal_panel,
)

from nsealgo.backtest.engine import run_backtest
from nsealgo.costs import CostModel

panel, symbols, _ = load()
P, T = 10, 0.01
sig = signal_panel(panel, P, T)
sc = score_from_signal(sig, panel, P)
tr = sig.loc[TRAIN_START:TRAIN_END]

res = backtest(panel, sc, TRAIN_START, TRAIN_END)
w = res.weights
nc = (w > 0).sum(axis=1)
gross = w.sum(axis=1)

print("TRAIN structural diagnostics -- champion V2 (period=10, threshold=0.01)")
print(f"  avg names held      : {nc.mean():.2f}   (engine cap max_names={PCFG.max_names})")
print(f"  max names held      : {nc.max()}   | days at the cap: {int((nc >= PCFG.max_names).sum())}")
print(f"  min names held      : {nc.min()}   | days fully in cash (<=1 name): {int((nc <= 1).sum())}")
print(f"  avg gross exposure  : {gross.mean() * 100:.1f}%  (cap = {(1 - PCFG.cash_buffer) * 100:.0f}%)")
print(f"  avg cash            : {(1 - gross.mean()) * 100:.1f}%")
print(f"  max single weight   : {w.max().max() * 100:.2f}% (cap {PCFG.max_weight * 100:.0f}%)")
print(f"  signal liveness     : {live_frac(tr) * 100:.1f}% of symbol-days long "
      f"(>5% floor)  |  short {float((tr < 0).to_numpy().mean()) * 100:.1f}%  flat {float((tr == 0).to_numpy().mean()) * 100:.1f}%")
print(f"  flagged names/day   : median {tr.gt(0).sum(axis=1).median():.0f}  "
      f"p10 {tr.gt(0).sum(axis=1).quantile(.1):.0f}  p90 {tr.gt(0).sum(axis=1).quantile(.9):.0f}")

# gross (zero-cost) vs net, to expose how much of the result costs eat

res0 = run_backtest(panel.loc[TRAIN_START:TRAIN_END], sc.loc[TRAIN_START:TRAIN_END],
                    CostModel(segment="delivery", slippage_bps=Decimal("0"),
                              brokerage_per_order=Decimal("0")), PCFG)
print(f"\n  NET  (delivery, 5bps slippage): CAGR {res.metrics.cagr * 100:6.2f}%  "
      f"Sharpe {res.metrics.sharpe:5.2f}  drag {res.metrics.cost_drag_annual * 100:.2f}%/y")
print(f"  ZERO-COST diagnostic only      : CAGR {res0.metrics.cagr * 100:6.2f}%  "
      f"Sharpe {res0.metrics.sharpe:5.2f}")
print(f"  -> cost is the difference between those two CAGRs: "
      f"{(res0.metrics.cagr - res.metrics.cagr) * 100:.2f} pp/yr")

print("\n  train-year CAGR (net):")
ey = res.equity.resample("YE").last()
yr = ey.pct_change()
yr.iloc[0] = ey.iloc[0] - 1
print("   " + "  ".join(f"{d.year}:{v*100:6.2f}%" for d, v in yr.items()))

nc_y = nc.groupby(nc.index.year).mean()
print("\n  avg names held per year (accumulation check):")
print("   " + "  ".join(f"{y}:{v:.1f}" for y, v in nc_y.items()))
print(f"   first 3y mean {nc_y.iloc[:3].mean():.2f}  ->  last 3y mean {nc_y.iloc[-3:].mean():.2f}  "
      f"(flat => no residual accumulation)")
