"""Definitive no-lookahead test for the full signal -> score -> weights pipeline.

Method: build weights twice on the SAME date range, once from the full panel and once
from a panel TRUNCATED at some date. If any future bar leaks into a past decision, the
weights before the cut will differ between the two runs. This tests the whole chain
(signal_panel -> score_from_signal -> run_backtest), not just the indicators.

A weaker sanity check is included too: shifting the score one extra day forward must
DEGRADE performance (if an extra day of lag were harmless, the engine would already be
peeking or the signal would be noise).
"""
from __future__ import annotations

import sys

import pandas as pd

sys.path.insert(0, "src")
sys.path.insert(0, "research/agent_correlation_gate")

from common import (  # noqa: E402
    TEST_END,
    TEST_START,
    backtest,
    load,
    score_from_signal,
    signal_panel,
)

panel, _, _ = load()
PERIOD, THR = 10, 0.01
score = score_from_signal(signal_panel(panel, PERIOD, THR), panel, PERIOD)

print("TEST 1 -- weights must not depend on future data (truncation test)")
full = backtest(panel, score, TEST_START, TEST_END)
worst = 0.0
for cut in ("2024-06-28", "2024-12-31", "2025-06-30", "2025-12-31", "2026-03-31"):
    cut = pd.Timestamp(cut, tz=panel.index.tz)
    trunc_panel = panel.loc[:cut]
    trunc_score = score.loc[:cut]
    t = backtest(trunc_panel, trunc_score, TEST_START, cut)
    # compare weights on the overlapping dates
    ov = t.weights.index.intersection(full.weights.index)
    d = (t.weights.loc[ov] - full.weights.loc[ov]).abs().to_numpy()
    mx = float(d.max()) if d.size else 0.0
    worst = max(worst, mx)
    rmax = float((t.returns - full.returns.reindex(t.returns.index)).abs().max())
    print(f"  cut at {cut}: {len(ov):4d} overlapping bars | max |Δweight| = {mx:.3e} | "
          f"max |Δreturn| = {rmax:.3e}  {'OK' if mx < 1e-12 else 'LOOKAHEAD LEAK'}")
print(f"\n  worst deviation across all cuts: {worst:.3e} -> "
      f"{'PASS - no lookahead' if worst < 1e-12 else 'FAIL - future data leaks'}")

print("\nTEST 2 -- an extra day of lag must hurt (else the engine is peeking or signal is noise)")
base = backtest(panel, score, TEST_START, TEST_END)
print(f"  as designed      CAGR {base.metrics.cagr * 100:7.2f}%  Sharpe {base.metrics.sharpe:6.2f}")
for lag in (1, 2):
    lagged = backtest(panel, score.shift(lag), TEST_START, TEST_END)
    print(f"  score.shift({lag})    CAGR {lagged.metrics.cagr * 100:7.2f}%  "
          f"Sharpe {lagged.metrics.sharpe:6.2f}  "
          f"(delta CAGR {lagged.metrics.cagr * 100 - base.metrics.cagr * 100:+.2f} pp)")

print("\nTEST 3 -- same check on TRAIN, where the champion was actually chosen")
TR_S = pd.Timestamp("2016-01-01", tz=panel.index.tz)
TR_E = pd.Timestamp("2023-12-31", tz=panel.index.tz)
tr_full = backtest(panel, score, TR_S, TR_E)
worst_tr = 0.0
for cut in ("2017-06-30", "2019-12-31", "2022-06-30"):
    cut = pd.Timestamp(cut, tz=panel.index.tz)
    t = backtest(panel.loc[:cut], score.loc[:cut], TR_S, cut)
    ov = t.weights.index.intersection(tr_full.weights.index)
    worst_tr = max(worst_tr, float((t.weights.loc[ov] - tr_full.weights.loc[ov]).abs().to_numpy().max()))
print(f"  worst |Δweight| on TRAIN truncation: {worst_tr:.3e} -> "
      f"{'PASS' if worst_tr < 1e-12 else 'FAIL'}")

print("\nTEST 4 -- score panel itself: rank must be built from <= t data only")
# NOTE: shift must be applied to the FULL panel, not to a slice -- shifting a slice
# makes the first `period` rows NaN and manufactures spurious mismatches.
rc = panel / panel.shift(PERIOD) - 1.0
sig_panel = signal_panel(panel, PERIOD, THR)
mism = 0
for d in panel.loc["2025-03-01":"2025-06-30"].index[::15]:
    full_row = (panel.loc[d] / panel.loc[:d].iloc[-PERIOD - 1] - 1.0)
    live = sig_panel.loc[d] > 0
    mine = rc.loc[d].where(live).rank(pct=True)
    ref = full_row.where(live).rank(pct=True)
    # NaN-aware equality: .ne() reports NaN != NaN as True, which is an artefact of
    # the comparison, not a disagreement. Compare only where either side is defined.
    both = mine.notna() | ref.notna()
    mism += int((mine[both].ne(ref[both])).sum())
print(f"  sampled rows with rank mismatch vs an independent recompute: {mism} -> "
      f"{'PASS' if mism == 0 else 'FAIL'}")
print(f"  NaN share of score (names the strategy called flat): "
      f"{float(score.loc[TEST_START:TEST_END].isna().to_numpy().mean()) * 100:.1f}%")
