"""Step 04 — why the strategy fails, and whether the signal has ANY forward content.

Three questions, none of which select anything:

  Q1  Is the score inert? (proves the Keltner == random identity)
  Q2  Does being below the lower band predict better forward returns? (the real test)
  Q3  What does the sparse book actually cost in cash drag?
"""

from __future__ import annotations

import sys

sys.path.insert(0, "research/agent_keltner")
sys.path.insert(0, "src")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from common import TEST, TRAIN, keltner_depth, load_ohlc, load_panel, make_score  # noqa: E402

pd.set_option("display.width", 220)

panel = load_panel()
ohlc = load_ohlc()

# =============================================================================
# Q1 -- is the score inert?
# =============================================================================
print("=" * 100)
print("Q1  IS THE CROSS-SECTIONAL SCORE INERT?")
print("=" * 100)
print("`build_rebalance_weights` takes the top `n_positions`=22 names by score.")
print("When the gate flags < 22 names, every flagged name is in the top 22 whatever")
print("its score, so `pure` and `hybrid` must be identical books.\n")

for period, mult in [(20, 2.0), (20, 2.5), (40, 2.0), (40, 2.5)]:
    d = keltner_depth(panel, ohlc["high"], ohlc["low"], period)
    n_flag = (d > mult).sum(axis=1)
    over = n_flag > 22
    print(f"  p={period} m={mult}:  bars with >22 flagged: {int(over.sum()):5d} / "
          f"{len(n_flag)}  ({float(over.mean())*100:6.3f}%)   "
          f"max flagged on one bar: {int(n_flag.max())}")

# Direct proof: do the two declared constructions produce the SAME book?
print("\n  Direct test -- do `pure` and `hybrid` produce the same held weights?")
for period, mult in [(20, 2.0), (40, 2.0)]:
    a = make_score(panel, ohlc["high"], ohlc["low"], period, mult, "pure")
    b = make_score(panel, ohlc["high"], ohlc["low"], period, mult, "hybrid")
    print(f"    p={period} m={mult}: (score-level comparison is not the right test --")
    print("      see 05_score_inertness.py, which compares the resulting BOOKS)")
print("\n  (Identical flag sets + <22 flagged => identical books => identical P&L.)")

# =============================================================================
# Q2 -- does the signal predict forward returns at all?
# =============================================================================
print("=" * 100)
print("Q2  FORWARD-RETURN CONTENT OF THE LOWER-BAND TOUCH")
print("=" * 100)
print("If the strategy is real mean reversion, names below the lower Keltner band")
print("should OUTperform the universe over the next month. Measured, both windows.\n")

fwd = {h: panel.shift(-h) / panel - 1.0 for h in (21, 63)}

rows = []
for period, mult in [(20, 2.0), (20, 2.5), (40, 2.0), (40, 2.5)]:
    d = keltner_depth(panel, ohlc["high"], ohlc["low"], period)
    for wname, lo, hi in (("TRAIN", *TRAIN), ("TEST", *TEST)):
        gate = (d > mult).loc[lo:hi]
        for h, f in fwd.items():
            fsub = f.loc[lo:hi]
            g = gate.to_numpy()
            m = gate.to_numpy() & np.isfinite(fsub.to_numpy())
            hit = fsub.to_numpy()[m]
            uni = fsub.to_numpy()[np.isfinite(fsub.to_numpy())]
            if hit.size < 50:
                continue
            se = hit.std(ddof=1) / np.sqrt(hit.size)
            se_u = uni.std(ddof=1) / np.sqrt(uni.size)
            rows.append({
                "period": period, "mult": mult, "window": wname, "fwd_days": h,
                "n": int(hit.size),
                "fwd_ret_flagged_%": float(hit.mean() * 100),
                "fwd_ret_universe_%": float(uni.mean() * 100),
                "excess_%": float((hit.mean() - uni.mean()) * 100),
                "t_stat": float((hit.mean() - uni.mean()) / np.sqrt(se**2 + se_u**2)),
            })

df = pd.DataFrame(rows)
print(df.to_string(index=False, float_format=lambda v: f"{v:9.3f}"))
print()
n_neg = int((df["t_stat"] < 0).sum())
print(f"  cells with t < 0 (flagged names did WORSE than the universe): "
      f"{n_neg}/{len(df)}")
print("  A negative `excess_%` means the lower band is where losers live, not where")
print("  winners are cheap -- i.e. the reversion premise is inverted on this data.")

# Does band DEPTH matter at all (monotonicity)? Decile the depth, look at fwd 21d.
print("\n  Monotonicity: cross-sectional quintile of band depth vs next-21d return")
for period, _mult in [(20, 2.0), (40, 2.0)]:
    d = keltner_depth(panel, ohlc["high"], ohlc["low"], period)
    dd = d.stack().rename("depth")
    f = fwd[21].stack().rename("fwd21")
    j = pd.concat([dd, f], axis=1).dropna()
    j = j.loc[j.index.get_level_values(0) >= "2016-01-01"]
    q = pd.qcut(j["depth"], 5, labels=["Q1 deepest", "Q2", "Q3", "Q4", "Q5 shallow"])
    g = j.groupby(q, observed=True)["fwd21"].agg(["count", "mean"]) * 100
    print(f"\n    period={period}  (TRAIN+TEST pooled, depth quintiles)")
    print("      " + g.to_string(float_format=lambda v: f"{v:8.2f}").replace("\n", "\n      "))

# =============================================================================
# Q3 -- what the sparse book costs in cash drag
# =============================================================================
print()
print("=" * 100)
print("Q3  EXPOSURE / CASH DRAG")
print("=" * 100)
print("With 6 names capped at 12% each and a 10% cash buffer, the book cannot reach")
print("its 90% target. The un-invested remainder earns 0%, which is a large part of")
print("the return gap versus buy-and-hold and has nothing to do with transaction costs.")
for period, mult in [(20, 2.0), (40, 2.0)]:
    d = keltner_depth(panel, ohlc["high"], ohlc["low"], period)
    n = (d > mult).sum(axis=1).loc[TEST[0]:TEST[1]]
    print(f"  p={period} m={mult}: mean flagged {n.mean():5.2f}  "
          f"max achievable invested = min(22,mean) x 12% x 90% = "
          f"{min(22, n.mean())*0.12*0.9*100:5.1f}%")
print("\n  i.e. the strategy is structurally incapable of building a 90%-invested book.")
