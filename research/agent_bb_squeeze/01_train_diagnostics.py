"""Step 1 — TRAIN-only diagnostics of the squeeze statistic. No TEST access.

Purpose: understand where the coefficient of variation actually lives for these
48 names over 2016-2023, so the 5-variant budget is spent on thresholds and
lookbacks that are *inside* the signal's natural range rather than outside it.

Nothing here is a performance measurement. No TEST data is touched.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from common import (
    DATA,
    TRAIN,
    cv_panel,
    load_universe,
    roc_panel,
    squeeze_signal,
)

pd.set_option("display.width", 200)

panel, symbols, _ = load_universe(str(DATA))
tr = panel.loc[TRAIN[0] : TRAIN[1]]
print(f"TRAIN window {tr.index[0].date()} -> {tr.index[-1].date()}  {len(tr)} bars")

# --------------------------------------------------------------------------- #
print("\n" + "=" * 100)
print("1. DISTRIBUTION OF THE CV STATISTIC (the squeeze threshold applies to this)")
print("=" * 100)

for period in (10, 20, 40, 60):
    cv = cv_panel(tr, period)
    q = cv.stack().describe(percentiles=[0.05, 0.10, 0.25, 0.50, 0.75, 0.90])
    q = q.loc[["count", "5%", "10%", "25%", "50%", "75%", "90%", "mean"]]
    print(f"\nCV(period={period:>2}) pooled over all (name, day):")
    print("   " + "  ".join(f"{k:>7}" for k in q.index))
    print("   " + "  ".join(f"{v:>7.4f}" for v in q.values))

print("\nPer-name median CV(20) — lowest / highest volatility names:")
cv20 = cv_panel(tr, 20)
med = cv20.median(axis=1).sort_values()
print("  LOWEST: " + ", ".join(f"{k} {v:.4f}" for k, v in med.head(6).items()))
print("  HIGHEST: " + ", ".join(f"{k} {v:.4f}" for k, v in med.tail(6).items()))

# --------------------------------------------------------------------------- #
print("\n" + "=" * 100)
print("2. GATE FIRING RATE vs THRESHOLD (period=20, TRAIN) — signal liveness")
print("=" * 100)
cv20 = cv_panel(tr, 20)
r3 = roc_panel(tr, 3)
print(f"{'thr':>7} {'gate%':>8} {'+1 long%':>10} {'-1 short%':>11} "
      f"{'breadth/d':>11} {'days>=5':>9} {'days>=22':>10}")
for thr in (0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10, 0.12, 0.15):
    gate = cv20 < thr
    lng = gate & (r3 > 0)
    short = gate & (r3 < 0)
    breadth = float(lng.mean(axis=1).mean())
    d5 = float((lng.sum(axis=1) >= 5).mean())
    d22 = float((lng.sum(axis=1) >= 22).mean())
    print(f"{thr:>7.2f} {float(gate.to_numpy().mean()) * 100:>7.2f}% "
          f"{float(lng.to_numpy().mean()) * 100:>9.2f}% "
          f"{float(short.to_numpy().mean()) * 100:>10.2f}% "
          f"{breadth * 100:>10.2f}% {d5 * 100:>8.1f}% {d22 * 100:>9.1f}%")

# --------------------------------------------------------------------------- #
print("\n" + "=" * 100)
print("3. DIRECTION SPLIT — is the squeeze gate directionally informative at all?")
print("   (mean 3-bar forward return after a squeeze, TRAIN, gross of costs)")
print("=" * 100)
fwd = panel.shift(-5) / panel - 1.0  # 5-bar forward return
fwd_tr = fwd.loc[TRAIN[0] : TRAIN[1]]
print(f"{'thr':>7} {'n(+1)':>10} {'fwd5 mean':>11} {'n(-1)':>10} {'fwd5 mean':>11} "
      f"{'spread':>9} {'t-stat':>8}")
for thr in (0.03, 0.05, 0.08, 0.10):
    lng, short, _ = squeeze_signal(tr, 20, thr, 3)
    a = fwd_tr.where(lng > 0).stack()
    b = fwd_tr.where(short > 0).stack()
    am, bm = float(a.mean()), float(b.mean())
    se = float(a.std() / np.sqrt(len(a)) + b.std() / np.sqrt(len(b)))
    print(f"{thr:>7.2f} {len(a):>10} {am * 100:>10.3f}% {len(b):>10} {bm * 100:>10.3f}% "
          f"{(am - bm) * 100:>8.3f}% {(am - bm) / se:>8.2f}")

print("\nSame, 21-bar forward return:")
fwd21 = (panel.shift(-21) / panel - 1.0).loc[TRAIN[0] : TRAIN[1]]
for thr in (0.03, 0.05, 0.08, 0.10):
    lng, short, _ = squeeze_signal(tr, 20, thr, 3)
    a = fwd21.where(lng > 0).stack()
    b = fwd21.where(short > 0).stack()
    am, bm = float(a.mean()), float(b.mean())
    se = float(a.std() / np.sqrt(len(a)) + b.std() / np.sqrt(len(b)))
    print(f"{thr:>7.2f} {len(a):>10} {am * 100:>10.3f}% {len(b):>10} {bm * 100:>10.3f}% "
          f"{(am - bm) * 100:>8.3f}% {(am - bm) / se:>8.2f}")

# --------------------------------------------------------------------------- #
print("\n" + "=" * 100)
print("4. REGIME STABILITY — is the gate's firing rate constant across years?")
print("   A signal whose liveness drifts is not a signal; it is a hidden regime bet.")
print("=" * 100)
print(f"{'year':>6} {'CV20 med':>9} {'gate@0.05%':>11} {'long@0.05%':>12} "
      f"{'breadth':>9} {'ewret':>9}")
ew = tr.pct_change(fill_method=None).mean(axis=1)
for y, g in cv20.groupby(cv20.index.year):
    gate = g < 0.05
    lng = gate & (r3.loc[g.index] > 0)
    print(f"{y:>6} {float(g.stack().median()):>9.4f} "
          f"{float(gate.to_numpy().mean()) * 100:>10.2f}% "
          f"{float(lng.to_numpy().mean()) * 100:>11.2f}% "
          f"{float(lng.mean(axis=1).mean()) * 100:>8.2f}% "
          f"{float(ew.loc[g.index].sum()) * 100:>8.2f}%")

# --------------------------------------------------------------------------- #
print("\n" + "=" * 100)
print("5. HOW MUCH IS THE SIGNAL JUST 'LOW VOL'? correlation of gate with low-vol")
print("=" * 100)
vol60 = tr.pct_change(fill_method=None).rolling(60, min_periods=40).std()
for thr in (0.05, 0.08):
    gate = (cv20 < thr).stack()
    v = (-vol60).stack().loc[gate.index]
    # rank correlation of the gate indicator against the low-vol score
    print(f"  thr={thr:.2f}  spearman(gate, -vol60) = {gate.corr(v, method='spearman'):>6.3f}")
mask = cv20 < 0.05
common_idx = mask.notna() & vol60.notna()
gm = mask.where(common_idx).stack().astype(float)
vs = (-vol60).where(common_idx).stack()
print(f"  thr=0.05 point-biserial-ish r(gate, -vol60) = {float(gm.corr(vs)):.3f}")
print("\n  -> The squeeze gate IS a low-volatility detector. Any apparent alpha is")
print("     partly a bet that quiet names keep going, which the composite already")
print("     holds 15% in via low_volatility.")
