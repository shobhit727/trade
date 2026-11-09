"""Step 05 — TRAIN-ONLY mechanism diagnosis. NOT a variant, consumes no budget.

Three questions the pipeline raised but did not answer cleanly:

1. `pure` construction ranks gated names by oversold DEPTH (-sig, deepest first).
   Does depth predict forward return WITHIN the gated set? If the deepest names are
   the worst, the construction is self-defeating: it buys precisely the sub-bucket
   that underperforms. That is a defect of the port, not of the catalog strategy.

2. Reconcile 03's "reversion CONFIRMED OOS" (unconditional bucket corr) with 04's
   "no excess" (cross-sectionally demeaned, Newey-West). The unconditional measure
   carries the market factor.

3. Period matters: 04(b) evaluates the LOCKED variant (period=60), while 01/02b bucket
   tables used the catalog default (period=20). Both are reported side by side so the
   difference is visible rather than hidden.

All work here is TRAIN-only. TEST is not touched.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "research/agent_bollinger_bands")
sys.path.insert(0, "src")

import numpy as np
import pandas as pd
from common import TRAIN, bollinger_position, gate, load_panel

panel = load_panel().loc[: TRAIN[1]].copy()
fwd = (panel.shift(-21) / panel - 1.0)
BINS = [-np.inf, -3, -2.5, -2.25, -2.0]
LABS = ["<-3", "-3..-2.5", "-2.5..-2.25", "-2.25..-2"]
MID = np.array([-3.25, -2.75, -2.375, -2.125])


def bucket_table(period: int, demean: bool) -> pd.DataFrame:
    z = bollinger_position(panel, period, 2.0) * 2.0
    g = gate(bollinger_position(panel, period, 2.0), 1.0)
    y = fwd.sub(fwd.mean(axis=1), axis=0) if demean else fwd
    zf, gf, yf = z.to_numpy().ravel(), g.to_numpy().ravel(), y.to_numpy().ravel()
    ok = np.isfinite(zf) & np.isfinite(yf) & gf
    d = pd.DataFrame({"z": zf[ok], "y": yf[ok]})
    d["b"] = pd.cut(d["z"], bins=BINS, labels=LABS)
    return d.groupby("b", observed=True)["y"].agg(["count", "mean"])


print("=" * 100)
print("1) DOES DEPTH PREDICT RETURN *WITHIN* THE GATED SET?  (TRAIN only)")
print("   `pure` ranks by -sig, so the DEEPEST names get the top score.")
print("=" * 100)
for period in (20, 60):
    ag = bucket_table(period, demean=False)
    print(f"\n  period={period}  (universe mean 21d fwd "
          f"{float(np.nanmean(fwd.to_numpy()))*1e4:,.1f} bps)")
    for k in ag.index:
        print(f"    z {str(k):<12} n={int(ag.loc[k,'count']):>5}  "
              f"mean fwd {ag.loc[k,'mean']*1e4:>8,.1f} bps")
    c = float(np.corrcoef(MID, ag["mean"].to_numpy())[0, 1])
    print(f"    corr(depth midpoint, mean fwd) within gate = {c:+.3f}")
    print(f"    -> {'DEEPEST IS WORST: `pure` buys the worst sub-bucket (self-defeating)' if c > 0.7 else 'shallowest is worst' if c < -0.7 else 'no clear depth ordering'}")

print("\n  CONSEQUENCE: when depth is counterproductively ordered, `pure` is guaranteed")
print("  to select the worst names inside its own gate. This is a defect of the SCORE")
print("  CONSTRUCTION I chose to isolate the signal, NOT a property of the catalog")
print("  strategy. The catalog emits an unranked +1/0/-1 and says nothing about depth.")

print("\n" + "=" * 100)
print("2) RECONCILING 03 ('reversion CONFIRMED OOS') WITH 04 ('no excess')")
print("   03 used an UNCONDITIONAL bucket correlation; 04 used a cross-sectionally")
print("   demeaned, Newey-West-adjusted excess. The unconditional measure carries the")
print("   common market factor.")
print("=" * 100)
for period in (20, 60):
    raw = bucket_table(period, demean=False)
    dm = bucket_table(period, demean=True)
    print(f"\n  period={period}")
    print(f"    {'bucket':<12}{'RAW bps':>10}{'DEMEANED bps':>15}")
    for k in raw.index:
        print(f"    {str(k):<12}{raw.loc[k,'mean']*1e4:>10,.1f}{dm.loc[k,'mean']*1e4:>15,.1f}")

print("\n  The RAW column is contaminated: in a falling market the deepest-oversold")
print("  names have depressed raw returns, so z correlates negatively with raw return")
print("  and an unconditional test 'passes' for the wrong reason. The demeaned column")
print("  removes that, and what is left is small and of inconsistent sign — which is")
print("  exactly what 04's Newey-West test measures (TRAIN t=-0.92, TEST t=-1.21).")
print("\n  CORRECTION TO 03_test_eval.py: its line 'reversion CONFIRMED OOS' is")
print("  OVERSTATED and should not be read as evidence for the strategy. The")
print("  de-meaned, autocorrelation-adjusted excess is negative in BOTH windows.")
print("  There is no reversion edge to confirm.")

print("\n" + "=" * 100)
print("3) PERIOD SENSITIVITY — why 04(b) disagrees with the period=20 tables")
print("=" * 100)
print("  04(b) evaluates the LOCKED variant (period=60, gate z< -2.0).")
print("  01/02b bucket tables used the catalog default period=20.")
print("  Different baseline length changes which names are 'oversold' entirely, so the")
print("  two are not comparable numbers — they are different signals. Reported here so")
print("  the reader is not misled by comparing across them.")
for period in (20, 60):
    z = bollinger_position(panel, period, 2.0) * 2.0
    g = gate(bollinger_position(panel, period, 2.0), 1.0)
    per_day = g.sum(axis=1)
    print(f"  period={period}: liveness {float(g.to_numpy().mean()):.2%}  "
          f"names/day mean {per_day.mean():.2f}  median {per_day.median():.0f}")
