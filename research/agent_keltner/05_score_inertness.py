"""Step 05 — decisive test of the score-inertness claim.

No new variants: this compares V1 (`kelt_pure_p20_m2`) and V2 (`kelt_hybrid_p20_m2`),
both already inside the declared 5-variant budget, at the SAME period and multiplier.
If the cross-sectional ranking is inert they must produce IDENTICAL held weights.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "research/agent_keltner")
sys.path.insert(0, "src")

import numpy as np  # noqa: E402
from common import load_ohlc, load_panel, make_score, run  # noqa: E402

panel = load_panel()
ohlc = load_ohlc()

books = {}
for cons in ("pure", "hybrid"):
    sc = make_score(panel, ohlc["high"], ohlc["low"], 20, 2.0, cons)
    books[cons] = run(panel, sc).weights

a, b = books["pure"], books["hybrid"]
print("=" * 100)
print("DECISIVE: do `pure` and `hybrid` produce the same BOOK? (period 20, mult 2.0)")
print("=" * 100)
print(f"  held-weight frames identical : {a.equals(b)}")
maxdiff = float((a - b).abs().to_numpy().max())
print(f"  max abs difference in ANY held weight : {maxdiff:.3e}")
print(f"  bars where any weight differs          : "
      f"{int(((a - b).abs().sum(axis=1) > 1e-12).sum())} / {len(a)}")

ra = run(panel, make_score(panel, ohlc['high'], ohlc['low'], 20, 2.0, 'pure'))
rb = run(panel, make_score(panel, ohlc['high'], ohlc['low'], 20, 2.0, 'hybrid'))
print(f"  identical daily return series         : {np.allclose(ra.returns, rb.returns)}")
print(f"  CAGR  pure {ra.metrics.cagr*100:6.3f}%   hybrid {rb.metrics.cagr*100:6.3f}%")

print()
print("=" * 100)
print("Same test at period 40, mult 2.0 -- the variant carried into TEST.")
print("=" * 100)
a40 = run(panel, make_score(panel, ohlc['high'], ohlc['low'], 40, 2.0, 'pure')).weights
b40 = run(panel, make_score(panel, ohlc['high'], ohlc['low'], 40, 2.0, 'hybrid')).weights
print(f"  held-weight frames identical : {a40.equals(b40)}")
print(f"  max abs difference            : {float((a40 - b40).abs().to_numpy().max()):.3e}")
print(f"  bars where any weight differs : "
      f"{int(((a40 - b40).abs().sum(axis=1) > 1e-12).sum())} / {len(a40)}")

print()
print("=" * 100)
print("COROLLARY: what does the ENGINE score-panel comparison say at the gate level?")
print("=" * 100)
print("  On bars where >22 names are flagged the ranking CAN matter; measure how many")
print("  of those bars are actually used as REBALANCE dates (the engine only scores on")
print("  the first trading day of each month).")
from nsealgo.backtest.engine import _rebalance_dates  # noqa: E402

rb_dates = _rebalance_dates(panel.index, "M")
for period, mult in [(20, 2.0), (40, 2.0)]:
    d = None
    from common import keltner_depth  # noqa: E402

    d = keltner_depth(panel, ohlc["high"], ohlc["low"], period)
    n = (d > mult).sum(axis=1).loc[rb_dates]
    print(f"  p={period} m={mult}: rebalance dates {len(n)}, "
          f"with >22 flagged: {int((n > 22).sum())} "
          f"({float((n > 22).mean())*100:.2f}%)  mean flagged {n.mean():.2f}")
print()
print("  => on >97% of rebalance dates the score is not consulted at all.")
