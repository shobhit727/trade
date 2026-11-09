"""Step 2 — TRAIN-only. Probe the SELECTIVE end of the squeeze threshold.

Step 1 showed the catalog default thr=0.05 fires 85% of bars on NSE daily
data: the squeeze gate is effectively always-on, so "squeeze" carries no
information at the as-written value. This finds where the gate actually bites.
TRAIN only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from common import DATA, TRAIN, cv_panel, load_universe, roc_panel, squeeze_signal

pd.set_option("display.width", 200)
panel, symbols, _ = load_universe(str(DATA))
tr = panel.loc[TRAIN[0]:TRAIN[1]]
r3 = roc_panel(tr, 3)
fwd5 = (panel.shift(-5) / panel - 1.0).loc[TRAIN[0]:TRAIN[1]]
fwd21 = (panel.shift(-21) / panel - 1.0).loc[TRAIN[0]:TRAIN[1]]

print("=" * 104)
print("SELECTIVE RANGE — period=20, TRAIN. gate must be selective to mean anything.")
print("=" * 104)
cv20 = cv_panel(tr, 20)
print(f"{'thr':>7} {'gate%':>8} {'names/d':>9} {'fwd5 +1':>9} {'fwd5 -1':>9} "
      f"{'spread5':>9} {'t5':>6} {'fwd21 +1':>10} {'spread21':>9} {'t21':>6}")
for thr in (0.008, 0.010, 0.012, 0.015, 0.018, 0.020, 0.025, 0.030, 0.040):
    lng, short, _ = squeeze_signal(tr, 20, thr, 3)
    gate = cv20 < thr
    a, b = fwd5.where(lng > 0).stack(), fwd5.where(short > 0).stack()
    a21, b21 = fwd21.where(lng > 0).stack(), fwd21.where(short > 0).stack()
    s5, s21 = float(a.mean() - b.mean()), float(a21.mean() - b21.mean())
    t5 = s5 / float(a.std()/np.sqrt(len(a)) + b.std()/np.sqrt(len(b)))
    t21 = s21 / float(a21.std()/np.sqrt(len(a21)) + b21.std()/np.sqrt(len(b21)))
    print(f"{thr:>7.3f} {float(gate.to_numpy().mean())*100:>7.2f}% "
          f"{float(lng.sum(axis=1).mean()):>9.1f} {float(a.mean())*100:>8.3f}% "
          f"{float(b.mean())*100:>8.3f}% {s5*100:>8.3f}% {t5:>6.2f} "
          f"{float(a21.mean())*100:>9.3f}% {s21*100:>8.3f}% {t21:>6.2f}")

print("\n" + "=" * 104)
print("Same for period=40 (CV40 median 0.0368, so the scale shifts up)")
print("=" * 104)
cv40 = cv_panel(tr, 40)
print(f"{'thr':>7} {'gate%':>8} {'names/d':>9} {'spread5':>9} {'t5':>6} {'spread21':>9} {'t21':>6}")
for thr in (0.015, 0.020, 0.025, 0.030, 0.035, 0.040, 0.050):
    lng, short, _ = squeeze_signal(tr, 40, thr, 3)
    a, b = fwd5.where(lng > 0).stack(), fwd5.where(short > 0).stack()
    a21, b21 = fwd21.where(lng > 0).stack(), fwd21.where(short > 0).stack()
    s5, s21 = float(a.mean()-b.mean()), float(a21.mean()-b21.mean())
    t5 = s5/float(a.std()/np.sqrt(len(a)) + b.std()/np.sqrt(len(b)))
    t21 = s21/float(a21.std()/np.sqrt(len(a21)) + b21.std()/np.sqrt(len(b21)))
    print(f"{thr:>7.3f} {float((cv40<thr).to_numpy().mean())*100:>7.2f}% "
          f"{float(lng.sum(axis=1).mean()):>9.1f} {s5*100:>8.3f}% {t5:>6.2f} "
          f"{s21*100:>8.3f}% {t21:>6.2f}")

print("\n" + "=" * 104)
print("IS THE SELECTIVE SQUEEZE POPULATION EVEN INDEPENDENT OF THE BROAD ONE?")
print("If thr=0.015 is just 'the quietest 10% of the cross-section', the +1/-1")
print("split carries nothing, and the whole strategy reduces to low-vol + ROC3.")
print("=" * 104)
for period in (20, 40):
    cvx = cv_panel(tr, period)
    cvq = cvx.rank(axis=1, pct=True)   # within-day cross-sectional percentile of CV
    for q in (0.10, 0.20, 0.30):
        lng = (cvq < q) & (r3 > 0)
        short = (cvq < q) & (r3 < 0)
        a21 = fwd21.where(lng > 0).stack()
        b21 = fwd21.where(short > 0).stack()
        s21 = float(a21.mean()-b21.mean())
        t21 = s21/float(a21.std()/np.sqrt(len(a21)) + b21.std()/np.sqrt(len(b21)))
        print(f"  period={period} cross-sectional bottom-{q*100:.0f}% CV : "
              f"{float(lng.sum(axis=1).mean()):>5.1f} names/d  "
              f"spread21 {s21*100:>6.3f}%  t {t21:>5.2f}")
