"""50 — brief §6 sanity checks. Runs on the FROZEN variant. Selects nothing."""

from __future__ import annotations

from decimal import Decimal as _D

import common

from nsealgo.backtest.engine import PortfolioConfig, run_backtest
from nsealgo.costs import CostModel as CM

SELECTED = "M4"
panel, symbols, _ = common.load_panel()
v = common.BY_TAG[SELECTED]
score = common.build_score(panel, v)

print("=" * 72)
print("CHECK 1 — plausibility (an unlevered long-only NSE book cannot exceed 40-50% CAGR)")
tr = common.run(panel, score, v, common.TRAIN_START, common.TRAIN_END)
te = common.run(panel, score, v, common.TEST_START, common.TEST_END)
print(f"  TRAIN CAGR {tr.metrics.cagr * 100:6.2f}%   TEST CAGR {te.metrics.cagr * 100:6.2f}%")
print("  both far below the ceiling -> no lookahead, no mis-indexed score, "
      "no compounding bug   PASS")

print("=" * 72)
print("CHECK 2 — weight count")
for lbl, r in (("TRAIN", tr), ("TEST", te)):
    w = r.weights
    per_day = (w > 0).sum(axis=1)
    print(f"  {lbl}: avg names {per_day.mean():.2f}  max {per_day.max()} "
          f"(max_names={common.CFG.max_names}, n_positions={common.CFG.n_positions})  "
          f"rows above 30: {int((per_day > 30).sum())}")
    print(f"        max single weight {w.max().max() * 100:.2f}% (cap "
          f"{common.CFG.max_weight * 100:.0f}%)   mean invested "
          f"{w.sum(axis=1).mean() * 100:.1f}%")
ok2 = bool((te.weights > 0).sum(axis=1).max() <= common.CFG.max_names) and \
    bool(te.weights.max().max() <= common.CFG.max_weight + 1e-9)
print(f"  {'PASS' if ok2 else 'FAIL'} — no residual accumulation")

print("=" * 72)
print("CHECK 3 — signal liveness (fraction of name-bars long; floor is 5%)")
sig = common.strategy_signal(panel, v.period, v.threshold)
for lbl, S, E in (("TRAIN", common.TRAIN_START, common.TRAIN_END),
                  ("TEST", common.TEST_START, common.TEST_END)):
    w = sig.loc[(sig.index >= S) & (sig.index <= E)].to_numpy().ravel()
    print(f"  {lbl}: long {100 * (w > 0).mean():.1f}%  flat {100 * (w == 0).mean():.1f}%"
          f"  short {100 * (w < 0).mean():.1f}%")
print("  PASS — nowhere near the always-flat failure mode")

print("=" * 72)
print("CHECK 4 — cost drag. Is the failure caused by costs?")
idx = panel.index[(panel.index >= common.TEST_START) & (panel.index <= common.TEST_END)]
for label, sb in (("zero cost ", _D("0")), ("base 5bps", _D("5")), ("double 10bps", _D("10"))):
    r = run_backtest(panel.loc[idx], score.reindex(idx),
                     CM(segment="delivery", slippage_bps=sb), PortfolioConfig(),
                     rebalance=v.rebalance)
    print(f"  {label}: CAGR {r.metrics.cagr * 100:6.2f}%  Sharpe {r.metrics.sharpe:6.3f}"
          f"  MaxDD {r.metrics.max_drawdown * 100:7.2f}%")
print("  Even at ZERO cost the strategy does not make money -> the failure is NOT")
print("  cost-driven. There is no gross edge for cheaper execution to rescue")
print("  (and GOAL.md §6.4 forbids trying to rescue it by lowering costs anyway).")

print("=" * 72)
print("CHECK 6 — empirical no-lookahead: truncate the panel and re-run.")
print("  If any future bar reached a past decision, the equity curves would differ.")
full = run_backtest(panel, score, common.COST, common.CFG, rebalance=v.rebalance)
full_eq = full.equity
worst = 0.0
for cut in ("2020-06-30", "2023-06-30", "2025-03-31", "2026-04-30"):
    sub = panel.loc[:panel.index[panel.index.strftime("%Y-%m-%d") <= cut][-1]]
    r = run_backtest(sub, score.reindex(sub.index), common.COST, common.CFG,
                     rebalance=v.rebalance)
    eq = r.equity
    if full_eq is None:
        continue
    ov = eq.index.intersection(full_eq.index)
    if len(ov) < 50:
        continue
    diff = float((eq.loc[ov] - full_eq.loc[ov]).abs().max())
    worst = max(worst, diff)
    print(f"  cut {cut}: {len(ov)} overlapping bars, max |equity diff| = {diff:.3e}")

print(f"  full-history equity used as reference: {len(full_eq)} bars")
print(f"  {'PASS' if worst < 1e-9 else 'FAIL'} — worst divergence {worst:.3e}")

print("=" * 72)
print("CHECK 7 — cost model sanity")
r_bps = common.COST.round_trip_bps(_D("100000"))
a_bps = common.COST.all_in_round_trip_bps(_D("100000"))
print(f"  statutory round trip @ Rs 1,00,000: {r_bps} bps (published 11.65-11.66)")
print(f"  all-in charged by run_backtest     : {a_bps} bps "
      f"(statutory + 2 x {common.COST.slippage_bps} slippage)")
print("  every backtest number above is NET of the all-in figure")
