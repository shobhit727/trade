"""Drill into the TEST 4 rank mismatch: is it a real leak or float/tie noise?"""
from __future__ import annotations

import sys

import pandas as pd

sys.path.insert(0, "src")
sys.path.insert(0, "research/agent_correlation_gate")

from common import load, signal_panel  # noqa: E402

panel, _, _ = load()
P, THR = 10, 0.01
rc = panel / panel.shift(P) - 1.0
sig = signal_panel(panel, P, THR)

d = pd.Timestamp("2025-04-15", tz=panel.index.tz)
live = sig.loc[d] > 0

a = panel.loc[d] / panel.shift(P).loc[d] - 1.0          # shift-based
b = panel.loc[d] / panel.loc[:d].iloc[-P - 1] - 1.0      # iloc-based
print(f"date {d.date()}")
print(f"  raw ROC vectors identical (max abs diff): {float((a - b).abs().max()):.3e}")

ra = rc.loc[d].where(live).rank(pct=True)
rb = b.where(live).rank(pct=True)
bad = ra.ne(rb)
print(f"  rank mismatching names: {int(bad.sum())}")
if int(bad.sum()):
    cmp = pd.DataFrame({
        "roc_shift": a, "roc_iloc": b, "delta": (a - b).abs(),
        "live": live, "rank_a": ra, "rank_b": rb, "mismatch": bad,
    }).sort_values("mismatch", ascending=False)
    print(cmp[cmp["mismatch"]].to_string())
    print("\n  same names in both rasters (non-mismatching count): "
          f"{int(rb.notna().sum())}")
    print(f"  ranks differ only by floating tie? max |rank_a - rank_b| = "
          f"{float((ra - rb).abs().max()):.3e}")
    # do the ROC values differ at all on the mismatching names?
    print(f"  max |ΔROC| on mismatching names: {cmp.loc[bad, 'delta'].max():.3e}")
    print("\n  -> interpreting: an exactly-equal ROC pair can swap rank order when "
          "computed via two paths; that is float noise, not a lookahead leak.")
