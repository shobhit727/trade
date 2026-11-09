"""TEST window — touched exactly once, with the TRAIN-frozen winner V5_deep.

Order matters and is deliberate: the primary out-of-sample result is computed and
written to disk *before* any comparator or diagnostic runs, so the TEST number
cannot have influenced anything else.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from common import (
    CONFIG,
    COST,
    TEST_END,
    TEST_START,
    build_score,
    buy_and_hold,
    cci_panel,
    equal_weight_score,
    header,
    load_panels,
    run_variant,
    signal_panel,
    typical_price,
    yearly_returns,
)

from nsealgo.backtest.engine import run_backtest
from nsealgo.costs import STRESS_MODELS
from nsealgo.factors.core import build_composite_score

# FROZEN ON TRAIN (see TRAIN_RESULTS.txt): V5_deep = period 20, entry 100,
# monthly rebalance, rank_by "deepest".
FROZEN = dict(period=20, entry=100.0, rebalance="M", rank_by="deepest")
# Bar-level long fraction measured on TRAIN only (16.43%) — frozen too, so the
# random control cannot be accused of being fitted to TEST.
TRAIN_LONG_FRAC = 0.1643

p = load_panels()
close_all = p.close
tp_all = typical_price(p)
cci_all = cci_panel(tp_all, FROZEN["period"])

close = close_all.loc[TEST_START:TEST_END]
score_all = build_score(
    close_all, cci_all, FROZEN["entry"], rank_by=FROZEN["rank_by"]
)
score = score_all.loc[TEST_START:TEST_END]

print(header("PRIMARY RESULT — TEST 2024-01-01 -> 2026-10-01 (frozen V5_deep)"))
sig_test = signal_panel(cci_all, FROZEN["entry"]).loc[TEST_START:TEST_END]
n_fin = int((~np.isnan(cci_all.loc[TEST_START:TEST_END])).sum().sum())
test_long_frac = float((sig_test > 0).sum().sum()) / n_fin

primary = run_variant("CCI_V5_deep", close, score, rebalance=FROZEN["rebalance"])
m = primary.metrics

lines = []
lines.append("PRIMARY OOS RESULT (TEST 2024-01-01 -> 2026-10-01)")
lines.append("strategy: CCI(20) < -100 mean-reversion, rank most-oversold-first, monthly")
lines.append(f"bars={len(close)}  symbols={close.shape[1]}")
lines.append(f"CAGR            {m.cagr * 100:.2f}%")
lines.append(f"Sharpe          {m.sharpe:.2f}")
lines.append(f"MaxDD           {m.max_drawdown * 100:.2f}%  ({m.max_drawdown_days}d)")
lines.append(f"Calmar          {m.calmar:.2f}")
lines.append(f"Turnover        {m.annual_turnover:.2f}x/yr")
lines.append(f"Cost drag       {m.cost_drag_annual * 100:.2f}%/yr")
lines.append(f"Trades          {m.trades_per_year:.1f}/yr")
lines.append(f"Avg names held  {primary.avg_names:.1f}")
lines.append(f"Bar long frac   {test_long_frac * 100:.2f}%  (TRAIN: {TRAIN_LONG_FRAC * 100:.2f}%)")
yr = yearly_returns(primary.returns)
lines.append(f"Positive years  {int((yr > 0).sum())}/{len(yr)}")
for y, v in yr.items():
    lines.append(f"   {y}: {v * 100:>7.2f}%")
with open("PRIMARY_TEST_RESULT.txt", "w") as f:
    f.write("\n".join(lines) + "\n")

print("\n".join(lines))
print("\n>> wrote PRIMARY_TEST_RESULT.txt (frozen before comparators ran)")

# --------------------------------------------------------------------------- #
# Comparators and diagnostics
# --------------------------------------------------------------------------- #

print(header("TEST COMPARATORS"))


def show(label, r):
    mm = r.metrics
    print(
        f"{label:<28} CAGR {mm.cagr * 100:>7.2f}%  Sharpe {mm.sharpe:>6.2f}  "
        f"MaxDD {mm.max_drawdown * 100:>7.2f}%  Calmar {mm.calmar:>6.2f}  "
        f"Turn {mm.annual_turnover:>5.2f}x  Names {r.avg_names:>5.1f}"
    )


bh = buy_and_hold(close)  # panel.pct_change().mean(axis=1), net of one entry round trip
show("buy_and_hold equal-weight", bh)

ewb = run_variant("equal_weight_book", close, equal_weight_score(close))
show("equal_weight_book (engine)", ewb)

comp = build_composite_score(close_all).loc[TEST_START:TEST_END]
compr = run_variant("nsealgo_composite", close, comp, rebalance="M")
show("nsealgo_composite", compr)

print(header("GROSS vs NET (cost drag, same signals)"))
for nm, cm in (("zero_cost", STRESS_MODELS["zero_cost"]),
               ("base 5bps/side", COST),
               ("double_slippage", STRESS_MODELS["double_slippage"]),
               ("triple_slippage", STRESS_MODELS["triple_slippage"])):
    res = run_backtest(close, score, cm, CONFIG, rebalance=FROZEN["rebalance"])
    print(
        f"{nm:<20} CAGR {res.metrics.cagr * 100:>7.2f}%  Sharpe {res.metrics.sharpe:>6.2f}  "
        f"rt_bps {res.diag['round_trip_bps']:>6.2f}"
    )

print(header("RANDOM-SIGNAL NEGATIVE CONTROL (same bar-level long fraction)"))
from common import random_control  # noqa: E402

rc = random_control(
    close_all, cci_all, FROZEN["entry"], TRAIN_LONG_FRAC,
    FROZEN["rebalance"], n_seeds=20,
)
print(
    f"20 seeds, long_frac {rc['long_frac'] * 100:.2f}% (TRAIN-frozen), identical "
    f"engine/ranks/costs"
)
print(
    f"  random CAGR  mean {rc['cagr_mean'] * 100:>7.2f}%  median "
    f"{rc['cagr_median'] * 100:>7.2f}%  p05 {rc['cagr_p05'] * 100:>7.2f}%  "
    f"p95 {rc['cagr_p95'] * 100:>7.2f}%"
)
print(
    f"  random Sharpe mean {rc['sharpe_mean']:>6.2f}   random MaxDD mean "
    f"{rc['maxdd_mean'] * 100:>7.2f}%"
)
print(
    f"  CCI CAGR {m.cagr * 100:>7.2f}%  -> beats random mean by "
    f"{(m.cagr - rc['cagr_mean']) * 100:>7.2f} pp"
)
print(
    f"  CCI Sharpe {m.sharpe:>6.2f} -> beats random mean by "
    f"{m.sharpe - rc['sharpe_mean']:>6.2f}"
)

print(header("PLAUSIBILITY / BUG CHECKS"))
print(f"  CAGR {m.cagr * 100:.1f}%  -> under the 40-50% ceiling for an unlevered long-only book: "
      f"{'OK' if m.cagr < 0.50 else 'SUSPICIOUS'}")
print(f"  avg names {primary.avg_names:.1f}  -> not 48, no residual accumulation: "
      f"{'OK' if primary.avg_names < 30 else 'SUSPICIOUS'}")
print(f"  bar long frac {test_long_frac * 100:.1f}% -> above the 5% liveness floor: "
      f"{'OK' if test_long_frac > 0.05 else 'DEAD'}")
print(f"  cost drag {m.cost_drag_annual * 100:.2f}%/yr vs CAGR {m.cagr * 100:.2f}%")
pd.testing  # noqa: B018
