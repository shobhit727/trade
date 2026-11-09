"""Step 3 — fixed random controls (10 seeds) + the decisive diagnostic:
how much of the winning book is Williams %R and how much is just momentum?

If V4 (period=5) flags ~94% of symbol-days, the %R filter is nearly always ON and the
only thing shaping the book is the 126d momentum ranking applied to whatever passes.
This script measures that directly instead of asserting it.
"""

from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, "src")
sys.path.insert(0, os.path.dirname(__file__))

from harness import (  # noqa: E402
    ALL_IN_BPS,
    HDR,
    TEST,
    TRAIN,
    bh_score,
    load_hl,
    load_panel,
    random_score,
    row,
    run,
    signal_panel,
    slice_metrics,
    wr_score,
)

from nsealgo.factors.core import build_composite_score, momentum_6m, rank_cross_sectional  # noqa: E402
from nsealgo.provenance import provenance  # noqa: E402

panel, symbols, _ = load_panel()
H, L = load_hl(symbols, panel)

V4 = ("V4 fast-touch21", 5, -80.0, 21)
V2 = ("V2 canonical-touch21", 14, -80.0, 21)

print("PROVENANCE:", provenance())
print("\n--- RANDOM CONTROL, FIXED (continuous random scores), 10 seeds ---")
print(f"TRAIN {TRAIN[0].date()} -> {TRAIN[1].date()}, net of {ALL_IN_BPS} bps\n")
print(HDR)
print("-" * len(HDR))

for label, (_, p, lo_, pers) in [("V2 mask", V2), ("V4 mask", V4)]:
    sig = signal_panel(panel, H, L, p, lo_, pers)
    out = []
    for seed in range(1, 11):
        m, _, _ = slice_metrics(run(random_score(panel, sig, seed), panel), TRAIN, panel)
        out.append(m)
    cagr = np.array([o["CAGR%"] for o in out])
    shp = np.array([o["Sharpe"] for o in out])
    print(f"{'random@' + label + ' (mean)':<26}{cagr.mean():>8.2f}{shp.mean():>8.2f}"
          f"{np.mean([o['MaxDD%'] for o in out]):>8.2f}"
          f"{np.mean([o['Calmar'] for o in out]):>7.2f}"
          f"{np.mean([o['Turnover/y'] for o in out]):>8.2f}"
          f"{np.mean([o['CostDrag%/y'] for o in out]):>8.2f}"
          f"{np.mean([o['AvgNames'] for o in out]):>7.1f}"
          f"{np.mean([o['RupeesOn21L'] for o in out]):>12,.0f}")
    print(f"{'random@' + label + ' [min,max CAGR]':<26}"
          f"[{cagr.min():.2f},{cagr.max():.2f}]   Sharpe [{shp.min():.2f},{shp.max():.2f}]\n")

# ------------------------------------------------------------------ #
# DECISIVE DIAGNOSTIC: how different is the V4 book from a pure momentum book?
# ------------------------------------------------------------------ #
print("=" * 78)
print("DIAGNOSTIC — is V4's book just momentum?")
print("=" * 78)

sig4 = signal_panel(panel, H, L, *V4[1:])
sc4 = wr_score(panel, sig4)
mom_rank = rank_cross_sectional(momentum_6m(panel))  # pure momentum, every name

rb_idx = [d for d in panel.index if d.day <= 7]  # ~monthly rebalance dates
rb_idx = rb_idx[12:]  # warmup

ov, n_v4, n_pure = [], [], []
for d in rb_idx:
    a = sc4.loc[d].dropna().nlargest(22).index
    b = mom_rank.loc[d].dropna().nlargest(22).index
    n_v4.append(len(a))
    n_pure.append(len(b))
    if len(a) and len(b):
        ov.append(len(set(a) & set(b)) / len(set(a) | set(b)))

print(f"V4 top-22 names per rebalance : mean {np.mean(n_v4):.1f}")
print(f"pure-momentum top-22 per reb  : mean {np.mean(n_pure):.1f}")
print(f"Jaccard overlap V4 vs momentum: mean {np.mean(ov):.1%}  (median {np.median(ov):.1%})")
print()
print("Interpretation: overlap near 100% means the Williams %R filter is doing nothing")
print("and the entire result is the 126d momentum ranking.")

# ---- and what does pure momentum alone score? -------------------------------
res_pure = run(mom_rank, panel)
res_comp = run(build_composite_score(panel), panel)
res_bh = run(bh_score(panel), panel)
print()
print(HDR)
print("-" * len(HDR))
for nm, res in [("pure 126d momentum", res_pure), ("nsealgo composite", res_comp),
                ("buy-and-hold", res_bh)]:
    for win, wn in [(TRAIN, "TRAIN"), (TEST, "TEST")]:
        m, _, _ = slice_metrics(res, win, panel)
        print(row(f"{nm} [{wn}]", m))
    print()
