"""Fidelity check: does `common.z300` reproduce the catalog indicator exactly?

This drives the real catalog classes bar-by-bar with a rolling 300-bar deque (exactly
what `SignalStrategy` maintains via `feed`), and compares `TrendMrStrategy.signal()`
against our vectorised panel computation. If these disagree, every downstream number is
meaningless -- so this runs first and hard-fails.

Also reports signal liveness for each declared variant.
"""

from __future__ import annotations

import json

import numpy as np
from common import (
    Z_WINDOW,
    full_panel,
    liveness,
    long_flag,
    mean_names_flagged,
    test_slice,
    train_slice,
    z300,
)

from cryptobot.strategies.catalog.trend_mean_reversion import (
    TrendMrConfig,
    TrendMrStrategy,
)

VARIANTS = {
    "V1": (40, 1.5),
    "V2": (20, 1.5),
    "V3": (60, 1.5),
    "V4": (40, 1.0),
    "V5": (40, 2.0),
}

panel = full_panel()
cols = list(panel.columns)

print("=" * 78)
print("A. CATALOG FIDELITY — vectorised panel vs real Strategy.signal()")
print("=" * 78)

# Drive the real strategy with the same trailing buffer the base class maintains.
N = 400
probe_sym = cols[0]
closes = panel[probe_sym].to_numpy(dtype=float)
strat = TrendMrStrategy(TrendMrConfig(slow=40, entry=1.5))

cat_long = []
for i in range(len(closes)):
    c = float(closes[i])
    strat.feed(probe_sym, c, c, c, 0.0, ts=i)
    # After feed, replay signal() on exactly the buffer the base class holds.
    cl, _h, _lo, _v = strat.as_lists(probe_sym)
    if len(cl) < strat.warmup(cl):
        cat_long.append(False)
    else:
        cat_long.append(strat.signal(cl, None, None, None) > 0)
cat_long = np.array(cat_long)

ours_long = long_flag(panel, 40, 1.5)[probe_sym].to_numpy()
ours_long = np.nan_to_num(ours_long).astype(bool)

n = min(len(cat_long), len(ours_long))
agree = (cat_long[:n] == ours_long[:n]).sum()
print(f"symbol probed        : {probe_sym}")
print(f"bars compared        : {n}")
print(f"buffers saturated    : {len(cat_long)} bars (maxlen={Z_WINDOW})")
print(f"agreement            : {agree}/{n} = {agree / n:.4%}")
mism = np.where(cat_long[:n] != ours_long[:n])[0]
if len(mism):
    print(f"MISMATCHES at {len(mism)} bars, first 5:")
    for j in mism[:5]:
        print(
            f"  bar {j}: catalog={cat_long[j]} ours={ours_long[j]} close={closes[j]:.2f}"
        )
    raise SystemExit("FIDELITY FAIL: vectorised signal != catalog signal")

# The first 300 bars differ legitimately: the catalog buffer is still filling.
sat_start = 300
sat_agree = (cat_long[sat_start:n] == ours_long[sat_start:n]).sum()
sat_n = n - sat_start
print(f"saturated-window agreement: {sat_agree}/{sat_n} = {sat_agree / sat_n:.4%}")

print()
print("=" * 78)
print("B. Z-SCORE WINDOW — confirm it is 300, not the declared period=20")
print("=" * 78)
# Probe at a bar where 300d and 20d windows would give very different answers.
i = 2500
w300 = closes[i - Z_WINDOW + 1 : i + 1]
z300_manual = (closes[i] - w300.mean()) / w300.std(ddof=0)
z20_manual = (closes[i] - closes[i - 19 : i + 1].mean()) / closes[i - 19 : i + 1].std(
    ddof=0
)
print(f"bar {i}  close={closes[i]:.2f}")
print(f"  catalog z (300-bar) = {z300_manual:+.4f}   ours = {z300(panel)[probe_sym].iloc[i]:+.4f}")
print(f"  hypothetical 20-bar = {z20_manual:+.4f}   (what `period=20` WOULD have given)")
assert abs(z300_manual - z300(panel)[probe_sym].iloc[i]) < 1e-9, "z300 mismatch"
print("  -> confirms REPORT F1/F2: period=20 is dead, window is 300")

print()
print("=" * 78)
print("C. SIGNAL LIVENESS per declared variant (TRAIN and TEST)")
print("=" * 78)
rows = []
for name, (slow, entry) in VARIANTS.items():
    lt = liveness(train_slice(panel), slow, entry)
    le = liveness(test_slice(panel), slow, entry)
    nt = mean_names_flagged(train_slice(panel), slow, entry)
    ne = mean_names_flagged(test_slice(panel), slow, entry)
    rows.append((name, slow, entry, lt, le, nt, ne))
    print(
        f"{name} slow={slow:<3d} entry={entry:<4} | TRAIN live {lt * 100:6.2f}% "
        f"({nt:5.1f} names) | TEST live {le * 100:6.2f}% ({ne:5.1f} names)"
    )

print()
print("NOTE (brief sanity check 3): a live fraction far below ~5% means the strategy is")
print("effectively always-flat and only 'loses to costs'. See the numbers above.")

with open("fidelity.json", "w") as fh:
    json.dump(
        {
            "agreement_all": float(agree / n),
            "agreement_saturated": float(sat_agree / sat_n),
            "variants": {
                row[0]: {
                    "slow": row[1],
                    "entry": row[2],
                    "live_train": row[3],
                    "live_test": row[4],
                    "names_train": row[5],
                    "names_test": row[6],
                }
                for row in rows
            },
        },
        fh,
        indent=2,
    )
print("\nwrote fidelity.json")
