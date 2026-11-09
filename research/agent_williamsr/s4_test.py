"""Step 4 — THE TEST RUN.

Selection rule, fixed now on TRAIN alone (stated before this script is executed):
**the TRAIN winner by Sharpe wins.** From s2_train.py that is V4 `fast-touch21`
(period=5, lower=-80, touch-21), TRAIN Sharpe 0.76, ahead of V2 0.53, V5 0.36, V3 0.31, V1 -0.31.

Only V4 is evaluated on TEST. The other four variants are deliberately NOT run on TEST:
seeing all five out-of-sample would turn TEST into a second selection round, which is
exactly the discipline the protocol exists to prevent.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "src")
sys.path.insert(0, os.path.dirname(__file__))

from harness import (  # noqa: E402
    ALL_IN_BPS,
    HDR,
    TEST,
    ZERO_BPS,
    bh_score,
    load_hl,
    load_panel,
    random_score,
    row,
    run,
    signal_panel,
    slice_metrics,
    wr_score,
    year_ret,
)

from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.factors.core import build_composite_score  # noqa: E402
from nsealgo.provenance import provenance  # noqa: E402

ZERO = CostModel(segment="delivery", slippage_bps=0.0)  # statutory only = 11.92 bps

panel, symbols, _ = load_panel()
H, L = load_hl(symbols, panel)

V4 = (5, -80.0, 21)
sig4 = signal_panel(panel, H, L, *V4)
sc4 = wr_score(panel, sig4)

print("PROVENANCE:", provenance())
print("\nSELECTED ON TRAIN BY SHARPE: V4 fast-touch21 (period=5, lower=-80, touch-21)")
print("TRAIN Sharpe 0.76 vs V2 0.53, V5 0.36, V3 0.31, V1 -0.31.")
print(f"\n*** TEST {TEST[0].date()} -> {TEST[1].date()} — first and only evaluation ***\n")

res_v4 = run(sc4, panel)
res_bh = run(bh_score(panel), panel)
res_cmp = run(build_composite_score(panel), panel)

print(HDR)
print("-" * len(HDR))
rows = {}
m_v4, r_v4, eq_v4 = slice_metrics(res_v4, TEST, panel, ALL_IN_BPS)
m_bh, r_bh, eq_bh = slice_metrics(res_bh, TEST, panel, ALL_IN_BPS)
m_cmp, r_cmp, eq_cmp = slice_metrics(res_cmp, TEST, panel, ALL_IN_BPS)
rows["V4 WilliamsR (SELECTED)"] = m_v4
rows["buy-and-hold"] = m_bh
rows["nsealgo composite"] = m_cmp
for k, v in rows.items():
    print(row(k, v))

# ---- random control, TEST --------------------------------------------------
rnd = [slice_metrics(run(random_score(panel, sig4, s), panel), TEST, panel)[0]
       for s in range(1, 11)]
cagr = np.array([o["CAGR%"] for o in rnd])
shp = np.array([o["Sharpe"] for o in rnd])
print(f"{'random @V4 mask (10 seeds)':<26}{cagr.mean():>8.2f}{shp.mean():>8.2f}"
      f"{np.mean([o['MaxDD%'] for o in rnd]):>8.2f}"
      f"{np.mean([o['Calmar'] for o in rnd]):>7.2f}"
      f"{np.mean([o['Turnover/y'] for o in rnd]):>8.2f}"
      f"{np.mean([o['CostDrag%/y'] for o in rnd]):>8.2f}"
      f"{np.mean([o['AvgNames'] for o in rnd]):>7.1f}"
      f"{np.mean([o['RupeesOn21L'] for o in rnd]):>12,.0f}")
print(f"{'  random range':<26}CAGR [{cagr.min():.2f}, {cagr.max():.2f}]   "
      f"Sharpe [{shp.min():.2f}, {shp.max():.2f}]")

# ---- zero-cost control ----------------------------------------------------
print(f"\n--- ZERO-COST CONTROL ({ZERO_BPS} bps, statutory charges only) ---")
print(HDR)
print("-" * len(HDR))
z_v4, rz_v4, _ = slice_metrics(run(sc4, panel, cost=ZERO), TEST, panel, ZERO_BPS)
z_bh, rz_bh, _ = slice_metrics(run(bh_score(panel), panel, cost=ZERO), TEST, panel, ZERO_BPS)
print(row("V4 @ zero cost", z_v4))
print(row("buy-and-hold @ zero cost", z_bh))

# ---- calendar years -------------------------------------------------------
print("\n--- TEST calendar-year returns ---")
for k, r in [("V4 WilliamsR", r_v4), ("buy-and-hold", r_bh), ("nsealgo composite", r_cmp)]:
    print(f"{k:<26}{year_ret(r)}")

# ---- verdict arithmetic ---------------------------------------------------
print("\n" + "=" * 78)
print("VERDICT ARITHMETIC (TEST, net of 21.92 bps)")
print("=" * 78)
print(f"  V4 CAGR            {m_v4['CAGR%']:>8.2f}%")
print(f"  buy-and-hold CAGR  {m_bh['CAGR%']:>8.2f}%   -> V4 is "
      f"{m_v4['CAGR%'] - m_bh['CAGR%']:+.2f} pp/yr WORSE")
print(f"  V4 MaxDD           {m_v4['MaxDD%']:>8.2f}%")
print(f"  buy-and-hold MaxDD {m_bh['MaxDD%']:>8.2f}%   -> V4 is "
      f"{m_v4['MaxDD%'] - m_bh['MaxDD%']:+.2f} pp "
      f"{'DEEPER' if m_v4['MaxDD%'] < m_bh['MaxDD%'] else 'shallower'}")
print(f"  V4 Sharpe          {m_v4['Sharpe']:>8.2f}  vs random "
      f"{shp.mean():.2f} [{shp.min():.2f},{shp.max():.2f}]")
print(f"  V4 vs composite    {m_v4['CAGR%'] - m_cmp['CAGR%']:+.2f} pp/yr, "
      f"Sharpe {m_v4['Sharpe'] - m_cmp['Sharpe']:+.2f}")
print()
print(f"  Cost drag on V4        : {m_v4['CostDrag%/y']:.2f}%/y  "
      f"({m_v4['CostDrag%/y'] / max(m_bh['CostDrag%/y'], 1e-9):.1f}x buy-and-hold)")
print(f"  V4 gross-of-cost CAGR  : {z_v4['CAGR%']:.2f}%  "
      f"(zero-cost run; net is {m_v4['CAGR%']:.2f}%)")
print(f"  cost cliff            : {z_v4['CAGR%'] - m_v4['CAGR%']:.2f} pp/yr")
print()
print(f"  Rs 21,00,000 -> final  : {eq_v4.iloc[-1] * 21e5:,.0f} "
      f"(book started at Rs 21,00,000)")

pd.to_pickle({"v4_ret": r_v4, "bh_ret": r_bh, "cmp_ret": r_cmp}, "s4_test.pkl")
