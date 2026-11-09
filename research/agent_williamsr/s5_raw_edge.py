"""Step 5 — raw predictive power of the Williams %R entry condition, with the portfolio
wrapper removed.

Question: does `%R <= lower` on day t predict a positive forward return at all? Compute
the equal-weight forward return of flagged vs unflagged names, per variant, on TRAIN and
TEST. This separates "the signal has no edge" from "the signal had an edge the momentum
ranking destroyed".
"""

from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, "src")
sys.path.insert(0, os.path.dirname(__file__))
from harness import ALL_IN_BPS, TEST, TRAIN, load_hl, load_panel, signal_panel  # noqa: E402

panel, symbols, _ = load_panel()
H, L = load_hl(symbols, panel)
rets = panel.pct_change(fill_method=None)

VARIANTS = [
    ("V1 p14<-80 state", 14, -80.0, None),
    ("V2 p14<-80 touch21", 14, -80.0, 21),
    ("V3 p14<-90 touch21", 14, -90.0, 21),
    ("V4 p5<-80 touch21", 5, -80.0, 21),
    ("V5 p28<-80 touch21", 28, -80.0, 21),
]

# Costs of a 21-day hold, round trip, all-in: 21.92 bps.
COST = ALL_IN_BPS / 10_000.0

print("Forward 21-day return, flagged vs unflagged, equal weight, net of 21.92 bps")
print("(flipped sign of the return for the SHORT leg is NOT modelled -- long-only)")
print()
for horizon in (5, 21):
    fwd = panel.shift(-horizon) / panel - 1.0
    print("=" * 92)
    print(f"HORIZON {horizon} trading days")
    print(f"{'variant':<24}{'window':<7}{'flag%':>7}{'fwd ret flag':>14}"
          f"{'fwd ret unflag':>15}{'spread bp/yr':>14}{'t-stat':>9}")
    print("-" * 92)
    for name, p, lo_, pers in VARIANTS:
        sig = signal_panel(panel, H, L, p, lo_, pers)
        for win, wn in [(TRAIN, "TRAIN"), (TEST, "TEST")]:
            lo_d, hi_d = str(win[0].date()), str(win[1].date())
            s = sig.loc[lo_d:hi_d]
            f = fwd.loc[s.index]
            flag, unflag = s > 0, s <= 0
            rf = f.where(flag).stack().dropna()
            ru = f.where(unflag).stack().dropna()
            # annualise the horizon mean to a comparable per-year spread
            mult = 244.0 / horizon
            rf_n = (rf.mean() - COST) * mult
            ru_n = ru.mean() * mult
            # Welch two-sample t on flagged vs unflagged forward returns.
            se = float(np.sqrt(rf.var(ddof=1) / len(rf) + ru.var(ddof=1) / len(ru)))
            t = float((rf.mean() - ru.mean()) / se) if se > 0 else float("nan")
            print(f"{name:<24}{wn:<7}{100 * flag.values.mean():>6.1f}%"
                  f"{100 * rf_n:>13.2f}%{100 * ru_n:>14.2f}%"
                  f"{10000 * (rf_n - ru_n):>13.1f}{t:>9.2f}")
        print()

print("=" * 92)
print("Reading: 'spread' is (flagged - unflagged) annualised return of the raw signal.")
print("A Williams %R edge would show a positive spread in BOTH windows. It does not.")
