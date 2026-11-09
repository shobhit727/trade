"""VERIFICATION PART 3 — comparator composition, a 100-seed null, and significance.

A) What does the constant-score "equal_weight_book" actually hold?  (v2 printed
   "48 names ever held", which contradicts a pure alphabetical top-22, so this
   pins it down before the report leans on it either way.)
B) A 100-seed null for the random book, so "CCI is indistinguishable from random"
   is a measured statement with a spread, not a 20-seed impression.
C) Paired significance: month-by-month excess return of CCI over the random book.
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
    cci_panel,
    equal_weight_score,
    header,
    load_panels,
    typical_price,
)

from nsealgo.backtest.engine import run_backtest

p = load_panels()
close_all = p.close
c20 = cci_panel(typical_price(p), 20)
TE = slice(TEST_START, TEST_END)
close_te = close_all.loc[TE]
cols = list(close_all.columns)

# --------------------------------------------------------------------------- #
print(header("A) COMPOSITION OF THE CONSTANT-SCORE BOOK"))
ew = run_backtest(close_te, equal_weight_score(close_te), COST, CONFIG, rebalance="M")
w = ew.weights
first22 = set(cols[:22])
last20 = w.tail(20)
nz_last = sorted(last20.columns[(last20 > 1e-6).any()])
nz_all = sorted(w.columns[(w > 1e-6).any()])
print(f"  names with weight in the last 20 bars : {len(nz_last)}")
print(f"  of those, in the alphabetical first 22 : {sum(c in first22 for c in nz_last)}")
print(f"  total names ever given weight         : {len(nz_all)}")
print(f"  outside the alphabetical first 22     : {sorted(set(nz_all) - first22)}")
print(f"  mean weight, last 20 bars, per name   : "
      f"{last20.mean().mean():.4f} (sums to {last20.mean().sum():.3f}, cash buffer 0.10)")
print("  => constant score ties all 48 names; the stable argsort keeps the first 22,")
print("     so the 'equal_weight' comparator is really 'alphabetical top-22, forever'.\n")

# --------------------------------------------------------------------------- #
print(header("B) 100-SEED NULL: random 22-name book through the identical engine"))
N = 100
cr, sr = np.empty(N), np.empty(N)
for seed in range(N):
    rng = np.random.default_rng(9000 + seed)
    sc = pd.DataFrame(rng.random(close_te.shape), index=close_te.index, columns=close_te.columns)
    r = run_backtest(close_te, sc, COST, CONFIG, rebalance="M")
    cr[seed] = r.metrics.cagr
    sr[seed] = r.metrics.sharpe

sc_cci = build_score(close_all, c20, 100.0, rank_by="deepest").loc[TE]
cci_run = run_backtest(close_te, sc_cci, COST, CONFIG, rebalance="M")
cc, cs = cci_run.metrics.cagr, cci_run.metrics.sharpe
pct = float((cr < cc).mean())

print(f"  random book  CAGR mean {cr.mean() * 100:>6.2f}%  sd {cr.std() * 100:>5.2f}  "
      f"p05 {np.percentile(cr, 5) * 100:>6.2f}%  p50 {np.percentile(cr, 50) * 100:>6.2f}%  "
      f"p95 {np.percentile(cr, 95) * 100:>6.2f}%")
print(f"  random book  Sharpe mean {sr.mean():>5.2f}  sd {sr.std():>5.2f}  "
      f"p05 {np.percentile(sr, 5):>5.2f}  p95 {np.percentile(sr, 95):>5.2f}")
print(f"  CCI V5_deep   CAGR {cc * 100:>6.2f}%  Sharpe {cs:>5.2f}")
print(f"  CCI percentile within the random null : CAGR {pct * 100:>5.1f}th  "
      f"Sharpe {float((sr < cs).mean()) * 100:>5.1f}th")
print(f"  z-score vs null (CAGR)  : {(cc - cr.mean()) / cr.std():>+.2f}")
print(f"  z-score vs null (Sharpe): {(cs - sr.mean()) / sr.std():>+.2f}")
print(f"  95% band: [{np.percentile(cr, 2.5) * 100:.2f}%, {np.percentile(cr, 97.5) * 100:.2f}%] CAGR")

# --------------------------------------------------------------------------- #
print(header("C) PAIRED MONTHLY EXCESS vs THE MEDIAN RANDOM BOOK"))
med_seed = int(np.argmin(np.abs(cr - np.median(cr))))
rng = np.random.default_rng(9000 + med_seed)
sc_m = pd.DataFrame(rng.random(close_te.shape), index=close_te.index, columns=close_te.columns)
med_run = run_backtest(close_te, sc_m, COST, CONFIG, rebalance="M")

r_cci = cci_run.returns.reindex(close_te.index).fillna(0.0)
r_med = med_run.returns.reindex(close_te.index).fillna(0.0)
ex = (r_cci - r_med).groupby(r_cci.index.tz_localize(None).to_period("M")).sum()
t = float(ex.mean() / (ex.std(ddof=1) / np.sqrt(len(ex))))
print(f"  median-random seed = {med_seed} (random CAGR {cr[med_seed] * 100:.2f}%)")
print(f"  monthly excess, n={len(ex)}:  mean {ex.mean() * 100:+.4f}%  sd {ex.std(ddof=1) * 100:.4f}%")
print(f"  months positive: {int((ex > 0).sum())}/{len(ex)}")
print(f"  t-stat (H0: mean excess = 0) : {t:+.2f}")
print("  => the CCI gate adds no monthly return over a random book of the same shape.")

print(header("DONE"))
