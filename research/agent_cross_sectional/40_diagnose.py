"""Step 40 — WHY did it fail? Diagnostics on the signal itself, TRAIN vs TEST.

These are explanations, not new candidates. No parameter is selected here; V1 is
already frozen as the TEST result. Everything in this file is reported as a
diagnostic about the strategy's signal, computed identically on both windows so
the TRAIN->TEST change is visible.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "src")
sys.path.insert(0, "research/agent_cross_sectional")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from common import (  # noqa: E402
    TEST_START,
    TRAIN_START,
    build_score,
    strategy_signal,
)

from nsealgo.data.loader import load_universe  # noqa: E402

panel, symbols, _ = load_universe("data/nse")
P, T = 20, 0.015
H = 21  # forward horizon ~ one month

sig = strategy_signal(panel, P, T)
roc20 = panel / panel.shift(P) - 1.0
fwd = panel.shift(-H) / panel - 1.0  # forward 21-bar return, trailing-safe

windows = {
    "TRAIN 2016-2023": panel.loc[(panel.index >= TRAIN_START) & (panel.index < TEST_START)].index,
    "TEST  2024-2026": panel.loc[panel.index >= TEST_START].index,
}

print("=" * 78)
print("A. Does the strategy's own signal predict forward 21-bar returns?")
print("=" * 78)
print("   (long leg = ROC20 > 1.5%; short leg = ROC20 < -1.5%; flat = in between)")
print()
for label, idx in windows.items():
    s = sig.loc[idx].to_numpy()
    f = fwd.loc[idx].to_numpy()
    m = np.isfinite(s) & np.isfinite(f)
    s, f = s[m], f[m]
    print(f"  {label}")
    for name, code in (("long ", 1.0), ("flat ", 0.0), ("short", -1.0)):
        sel = s == code
        if sel.sum() == 0:
            continue
        r = f[sel]
        print(
            f"    {name} n={sel.sum():>7,}  mean fwd21d {r.mean() * 100:+6.3f}%  "
            f"ann {r.mean() * 244 / 21 * 100:+7.2f}%  "
            f"win {(r > 0).mean() * 100:5.1f}%  t={r.mean() / (r.std(ddof=1) / np.sqrt(len(r))):+5.2f}"
        )
    longm, shortm = f[s == 1.0], f[s == -1.0]
    spread = (longm.mean() - shortm.mean()) * 244 / 21 * 100
    print(f"    >>> long-minus-short annualised spread: {spread:+.2f} pp/yr")
    print()

print("=" * 78)
print("B. Rank IC between the 20d ROC and the forward 21-bar return")
print("=" * 78)
print("   Spearman-ish: cross-sectional corr of ROC20 with fwd21d, per day, averaged")
print()
for label, idx in windows.items():
    a = roc20.loc[idx].rank(axis=1)
    b = fwd.loc[idx].rank(axis=1)
    ics = [
        float(np.corrcoef(a.iloc[i], b.iloc[i])[0, 1])
        for i in range(len(a))
        if a.iloc[i].notna().sum() > 5 and b.iloc[i].notna().sum() > 5
    ]
    ics = pd.Series(ics)
    print(f"  {label}  mean IC {ics.mean():+.4f}  IC t-stat "
          f"{ics.mean() / (ics.std(ddof=1) / np.sqrt(len(ics))):+5.2f}  "
          f"(% days IC>0: {(ics > 0).mean() * 100:.1f}%)")
print()

print("=" * 78)
print("C. Horizon check — is 20d momentum working, or is 1-MONTH REVERSAL working?")
print("=" * 78)
print("   mean fwd21d return of the top-quintile ROC20 names, annualised")
print()
for label, idx in windows.items():
    a = roc20.loc[idx]
    b = fwd.loc[idx]
    for lb in (20, 60, 126):
        r = (panel / panel.shift(lb) - 1.0).loc[idx]
        top = r.rank(axis=1, pct=True) >= 0.8
        v = b.where(top).stack()
        print(f"  {label}  lookback {lb:>3}d: {v.mean() * 244 / 21 * 100:+7.2f}%/yr "
              f"(n={len(v):,})")
    print()

print("=" * 78)
print("D. Market regime over each window (was TEST a falling / choppy tape?)")
print("=" * 78)
for label, idx in windows.items():
    px = panel.loc[idx]
    r = px.pct_change(fill_method=None).mean(axis=1).fillna(0.0)
    eq = (1 + r).cumprod()
    dd = eq / eq.cummax() - 1.0
    ann = (eq.iloc[-1] ** (244 / len(eq)) - 1) * 100
    vol = r.std(ddof=1) * np.sqrt(244) * 100
    print(f"  {label}  equal-weight CAGR {ann:+6.2f}%  vol {vol:5.2f}%  "
          f"maxDD {dd.min() * 100:7.2f}%  frac days up {(r > 0).mean() * 100:.1f}%")
print()

print("=" * 78)
print("E. Is the threshold gate doing anything, or is this just 'top-22 of 48'?")
print("=" * 78)
elig = sig.gt(0).sum(axis=1)
print(f"   eligible names/day: mean {elig.mean():.1f} of 48 "
      f"(pct of days with >=22 eligible: {(elig >= 22).mean() * 100:.1f}%)")
print("   -> when >=22 names are eligible the gate is non-binding and the book is")
print("      exactly 'the 22 highest 20d ROC names'. Measured on TEST, that pure")
print("      ranking with NO gate is:")
for label, idx in windows.items():
    sc = (panel / panel.shift(P) - 1.0).loc[idx]  # no mask at all
    print(f"      {label}: eligible-gate active on {(elig.loc[idx] >= 22).mean() * 100:.0f}% of days")
print()
print("=" * 78)
print("F. Score-liveness: the fraction of the book actually attributable to the gate")
print("=" * 78)
for label, idx in windows.items():
    sc, s = build_score(panel.loc[idx], P, T, P)
    finite = sc.notna().sum(axis=1)
    print(f"  {label}: mean names with a usable score {finite.mean():.1f} / 48")
print()
print("(D and E are diagnostics. V1 stays frozen at the step-30 TEST result.)")
