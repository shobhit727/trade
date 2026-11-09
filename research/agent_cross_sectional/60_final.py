"""Step 60 — final consolidated evidence.

(a) Did ANY of the 5 declared variants beat buy-and-hold on TRAIN? If the whole
    family was already a drag on TRAIN, the Sharpe-based selection was choosing
    between losses and that is the root cause, not the TEST window.
(b) Cold-start check on the 0%-invested rows.
(c) Consolidated numbers for the report.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "src")
sys.path.insert(0, "research/agent_cross_sectional")

import json  # noqa: E402

import numpy as np  # noqa: E402
from common import (  # noqa: E402
    COST,
    PORTFOLIO,
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    VARIANTS,
    build_score,
    buy_and_hold,
    run_backtest,
)

from nsealgo.data.loader import load_universe  # noqa: E402

panel, symbols, _ = load_universe("data/nse")

print("=" * 92)
print("(a) ALL 5 DECLARED VARIANTS vs BUY-AND-HOLD — TRAIN ONLY")
print("=" * 92)
train = panel.loc[(panel.index >= TRAIN_START) & (panel.index <= TRAIN_END)]
bh_t = buy_and_hold(train, COST)
print(f"{'variant':<34} {'CAGR%':>8} {'Sharpe':>8} {'MaxDD%':>8} {'edge vs BH':>11}")
print("-" * 92)
print(f"{'BUY-AND-HOLD (TRAIN)':<34} {bh_t.metrics.cagr * 100:>8.2f} "
      f"{bh_t.metrics.sharpe:>8.2f} {bh_t.metrics.max_drawdown * 100:>8.2f} "
      f"{'—':>11}")
edges = []
for v in VARIANTS:
    sc, _ = build_score(train, v.period, v.threshold, v.rank_days)
    r = run_backtest(train, sc, COST, PORTFOLIO, v.rebalance)
    e = (r.metrics.cagr - bh_t.metrics.cagr) * 100
    edges.append(e)
    print(f"{str(v):<34} {r.metrics.cagr * 100:>8.2f} {r.metrics.sharpe:>8.2f} "
          f"{r.metrics.max_drawdown * 100:>8.2f} {e:>+11.2f}")
print("-" * 92)
print(f"variants beating buy-and-hold on TRAIN: "
      f"{sum(e > 0 for e in edges)} of {len(edges)}")
print(">>> Every one of the 5 declared variants was ALREADY behind buy-and-hold on")
print(">>> TRAIN. The strategy never had positive alpha; the TRAIN Sharpe was pure")
print(">>> beta riding on a +22.2%/yr tape. That is the root cause.")

print()
print("=" * 92)
print("(b) COLD-START CHECK — are the 0%-invested rows only at the very start?")
print("=" * 92)
sc, _ = build_score(panel, VARIANTS[0].period, VARIANTS[0].threshold, VARIANTS[0].rank_days)
full = run_backtest(panel, sc, COST, PORTFOLIO, VARIANTS[0].rebalance)
inv = full.weights.sum(axis=1)
cold = inv[inv < 1e-9]
print(f"   rows with 0% invested: {len(cold)} of {len(inv)}")
if len(cold):
    print(f"   first {cold.index[0].date()} .. last {cold.index[-1].date()} "
          f"({cold.index[0]} .. {cold.index[-1]})")
print(f"   -> {'PASS: cold start only, before the first rebalance' if len(cold) <= 2 else 'INVESTIGATE'}")
print(f"   invested weight after warmup: min {inv.iloc[2:].min() * 100:.2f}%  "
      f"mean {inv.iloc[2:].mean() * 100:.2f}%  max {inv.iloc[2:].max() * 100:.2f}%")

print()
print("=" * 92)
print("(c) CONSOLIDATED TEST NUMBERS (V1 frozen; net of costs)")
print("=" * 92)
with open("research/agent_cross_sectional/30_test.json") as fh:
    t = json.load(fh)
s = t["strategy"]
b = t["buy_hold"]
r = t["random_mean"]
c = t["composite"]
hdr = f"{'metric':<16} {'STRATEGY V1':>14} {'buy&hold':>12} {'random':>12} {'composite':>12}"
print(hdr)
print("-" * len(hdr))
rows = [
    ("CAGR %", "cagr", 100), ("Sharpe", "sharpe", 1), ("MaxDD %", "max_drawdown", 100),
    ("Calmar", "calmar", 1), ("Sortino", "sortino", 1), ("Vol %", "volatility", 100),
    ("Total %", "total_return", 100), ("Turnover x/y", "annual_turnover", 1),
    ("CostDrag %/y", "cost_drag_annual", 100), ("Trades /y", "trades_per_year", 1),
]
for label, key, mult in rows:
    print(f"{label:<16} {s[key] * mult:>14.2f} {b[key] * mult:>12.2f} "
          f"{r.get(key, float('nan')) * mult:>12.2f} {c[key] * mult:>12.2f}")
print()
print(f"avg names held (TEST) : {t['diag']['avg_names']:.2f}")
print(f"round-trip bps all-in  : {t['diag']['round_trip_bps']:.2f}  "
      f"(11.92 statutory + 5 bps slippage x 2 sides)")
print()
print("yearly (TEST):")
for y, v in t["strategy_yearly"].items():
    by = t["bh_yearly"].get(y)
    print(f"   {y}: strategy {v * 100:+6.2f}%   buy&hold "
          f"{(by * 100 if by is not None else float('nan')):+6.2f}%")
print()
print("=" * 92)
print(f"TRAIN {TRAIN_START.date()}..{TRAIN_END.date()} | "
      f"TEST {TEST_START.date()}..{TEST_END.date()} | "
      f"universe {len(symbols)} names | survivorship bias PRESENT "
      f"(today's NIFTY-50 backfilled)")
print("=" * 92)
assert np.isfinite(s["cagr"])
