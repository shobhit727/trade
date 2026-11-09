"""Why did TEST fail? Attribution, run AFTER the single TEST read.

No parameter changes here — this is diagnosis of an already-frozen result, so it
cannot contaminate the selection.

Three questions:
  Q1 Is the deficit a CASH-DRAG artefact? (strategy 73% invested vs b&h ~100%)
     -> re-run the same book scaled to 100% and compare.
  Q2 Is the flagged SET itself bad, or is the RANKING within it bad?
     -> equal-weight the whole flagged set, vs the top-ranked names we actually buy.
  Q3 What did we actually own, and who hurt?
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from common import (
    HDR,
    full_panel,
    long_flag,
    row,
    run,
    test_slice,
    tmr_score,
    train_slice,
)

sel = json.load(open("selected_variant.json"))
SLOW, ENTRY, MOM = sel["slow"], sel["entry"], sel["mom_days"]
panel = full_panel()
te = test_slice(panel)
score = test_slice(tmr_score(panel, SLOW, ENTRY))
flag = long_flag(panel, SLOW, ENTRY)
te_flag = test_slice(flag)

# --------------------------------------------------------------------------- #
# Q1 -- matched exposure. Does the deficit survive at 100% invested?
# --------------------------------------------------------------------------- #
print("=" * 78)
print("Q1  MATCHED-EXPOSURE TEST (is the shortfall just un-invested cash?)")
print("=" * 78)
res = run(te, score, label="as-run")
inv = float(res.weights.abs().sum(axis=1).mean())
print(f"as-run average invested: {inv * 100:.1f}%  -> CAGR {res.metrics.cagr * 100:.2f}%")

# Rescale the realised weights to full deployment. This is a DIAGNOSTIC on the
# already-selected book, not a new strategy: same names, same ranking, more cash.
w = res.weights.copy()
gross = w.abs().sum(axis=1).replace(0.0, np.nan)
w_full = w.div(gross, axis=0).fillna(0.0) * 0.99  # 99% deployed, no constraint breach

# Re-price the scaled book at the panel's realised returns.
rets = te.pct_change(fill_method=None).fillna(0.0)
port = (w_full.shift(1).fillna(0.0) * rets).sum(axis=1)
# charge the same turnover cost, scaled by the higher exposure
turn = float(res.metrics.annual_turnover)
from nsealgo.backtest.metrics import compute_metrics  # noqa: E402

eq = (1 + port).cumprod()
m_full = compute_metrics(port, eq)
print(f"same names @ ~99% invested          -> CAGR {m_full.cagr * 100:.2f}%  "
      f"Sharpe {m_full.sharpe:.2f}  (diagnostic, no cost re-charge)")

bh = te.pct_change(fill_method=None).mean(axis=1).fillna(0.0)
m_bh = compute_metrics(bh, (1 + bh).cumprod())
print(f"universe equal-weight (gross)        -> CAGR {m_bh.cagr * 100:.2f}%  "
      f"Sharpe {m_bh.sharpe:.2f}")
print()
print(f"=> at MATCHED exposure the strategy is "
      f"{(m_full.cagr - m_bh.cagr) * 100:+.2f} pts/yr vs the universe. "
      "Cash drag is therefore "
      f"{'NOT the main cause.' if (m_full.cagr - m_bh.cagr) < 0 else 'a real contributor.'}")

# --------------------------------------------------------------------------- #
# Q2 -- is the flagged set bad, or is the ranking within it bad?
# --------------------------------------------------------------------------- #
print()
print("=" * 78)
print("Q2  FLAGGED SET vs RANKING WITHIN THE SET")
print("=" * 78)
fwd = te.pct_change(fill_method=None).shift(-21)  # 1-month forward, diagnostic only
fw = panel.pct_change(fill_method=None).shift(-21)

set_ret = fw.where(te_flag).stack().groupby(level=0).mean()          # whole flagged set
uni_ret = fw.mean(axis=1)                                            # whole universe
cmp = pd.DataFrame({"flagged_set": set_ret, "universe": uni_ret}).dropna()
ann_f = (1 + cmp["flagged_set"]).prod() ** (252 / len(cmp)) - 1
ann_u = (1 + cmp["universe"]).prod() ** (252 / len(cmp)) - 1
print(f"annualised 21d-forward return, flagged set : {ann_f * 100:+.2f}%")
print(f"annualised 21d-forward return, whole universe: {ann_u * 100:+.2f}%")
print(f"=> the FILTER alone is {(ann_f - ann_u) * 100:+.2f} pts/yr. "
      "The rest of the gap is the momentum ranking on top.")

# Within the flagged set, compare the names we actually BUY (top of the rank,
# which is what lands in the book) against the WHOLE flagged set. `score` is only
# defined on flagged names, so the unheld flagged names are flagged & not-bought.
bought = score.notna() & (score >= 0.5)
b_ret = fw.where(bought).stack().groupby(level=0).mean()
s_ret = fw.where(te_flag).stack().groupby(level=0).mean()
cb = pd.DataFrame({"bought": b_ret, "whole_set": s_ret}).dropna()
if len(cb) == 0:
    a_b = a_r = float("nan")
else:
    a_b = (1 + cb["bought"]).prod() ** (252 / len(cb)) - 1
    a_r = (1 + cb["whole_set"]).prod() ** (252 / len(cb)) - 1
print()
print(f"within flagged set -> TOP-ranked (score>=0.5) 21d fwd : {a_b * 100:+.2f}%")
print(f"within flagged set -> WHOLE flagged set     21d fwd  : {a_r * 100:+.2f}%")
print(f"=> concentrating on the top-ranked names contributes {(a_b - a_r) * 100:+.2f} pts/yr.")
print(f"   (mean names with score>=0.5 per day: {float(bought.sum(axis=1).mean()):.1f})")

# --------------------------------------------------------------------------- #
# Q3 -- what did we own, and who hurt?
# --------------------------------------------------------------------------- #
print()
print("=" * 78)
print("Q3  WHAT WE OWNED (mean weight) AND WHO HURT")
print("=" * 78)
mw = res.weights.mean().sort_values(ascending=False)
mw = mw[mw > 1e-6]
print("top 12 by mean weight:")
tot_ret = (res.weights.shift(1).fillna(0.0) * rets).sum(axis=1)
for sym, wt in mw.head(12).items():
    contrib = float((res.weights[sym].shift(1).fillna(0.0) * rets[sym]).sum())
    te_ret = float(te[sym].pct_change(fill_method=None).add(1).prod() - 1)
    print(f"  {sym:<12s} mean_wt {wt * 100:5.2f}%   contrib {contrib * 100:+7.2f}%   "
          f"name return {te_ret * 100:+7.1f}%")
print()
tail = mw.tail(5)
print("bottom 5 by mean weight:")
for sym, wt in tail.items():
    contrib = float((res.weights[sym].shift(1).fillna(0.0) * rets[sym]).sum())
    te_ret = float(te[sym].pct_change(fill_method=None).add(1).prod() - 1)
    print(f"  {sym:<12s} mean_wt {wt * 100:5.2f}%   contrib {contrib * 100:+7.2f}%   "
          f"name return {te_ret * 100:+7.1f}%")

print()
print("=" * 78)
print("TRAIN vs TEST of the SAME frozen variant")
print("=" * 78)
tr_score = train_slice(tmr_score(panel, SLOW, ENTRY))
tr_res = run(train_slice(panel), tr_score, label="TRAIN frozen")
print(HDR)
print(row("TRAIN V4", tr_res.metrics, "selected here"))
print(row("TEST  V4", res.metrics, "one read"))
print(f"\nTRAIN Sharpe {tr_res.metrics.sharpe:+.2f} -> TEST Sharpe {res.metrics.sharpe:+.2f}")
print(f"TRAIN CAGR   {tr_res.metrics.cagr * 100:+.2f}%  -> TEST CAGR   {res.metrics.cagr * 100:+.2f}%")

# --------------------------------------------------------------------------- #
# D. Degenerate-spread check: is the 126d momentum spread even present in TEST?
# --------------------------------------------------------------------------- #
print()
print("=" * 78)
print("D  126d MOMENTUM SPREAD AMONG FLAGGED NAMES, BY YEAR")
print("=" * 78)
mom = panel / panel.shift(MOM) - 1.0
for yr in (2024, 2025, 2026):
    sl = slice(f"{yr}-01-01", f"{yr}-12-31")
    m_y = test_slice(mom.loc[sl].where(test_slice(flag).loc[sl]))
    spread = m_y.stack().groupby(level=0).agg(lambda s: s.max() - s.min()).mean()
    med = m_y.stack().groupby(level=0).median().mean()
    print(f"{yr}: mean cross-sectional spread of 126d mom among flagged = "
          f"{spread * 100:5.2f} pts   (median mom {med * 100:+.1f}%)")
print()
print("A near-zero or negative spread would mean 'extended above the 300d mean' and")
print("'high 126d momentum' are the same set, so the ranking has nothing to sort.")
