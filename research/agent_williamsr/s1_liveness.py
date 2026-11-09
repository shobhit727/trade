"""Step 1 — provenance, panel, cost sanity, and the signal-liveness diagnostic."""

from __future__ import annotations

import sys

import pandas as pd

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from harness import (  # noqa: E402
    TEST,
    TRAIN,
    cost_bps,
    load_panel,
    signal_panel,
)

from nsealgo.provenance import provenance  # noqa: E402

pd.set_option("display.width", 140)

print("=" * 78)
print("PROVENANCE:", provenance())
print("=" * 78)
print("COSTS:", cost_bps())
print()

panel, symbols, report = load_panel()
print(report.describe())
print(f"symbols kept: {len(symbols)}   panel shape: {panel.shape}")
print(f"panel span  : {panel.index[0].date()} -> {panel.index[-1].date()}")
print(f"TRAIN rows  : {panel.loc[slice(str(TRAIN[0].date()), str(TRAIN[1].date()))].shape[0]}")
print(f"TEST  rows  : {panel.loc[slice(str(TEST[0].date()), str(TEST[1].date()))].shape[0]}")
print()

# ---- need highs/lows for %R -------------------------------------------------
import os  # noqa: E402

from nsealgo.data.loader import load_symbol  # noqa: E402

highs, lows = {}, {}
for s in symbols:
    df = load_symbol(os.path.join("data/nse", f"{s}_1d.csv"), s)
    highs[s] = df["high"]
    lows[s] = df["low"]
H = pd.DataFrame(highs).reindex(panel.index)[symbols]
L = pd.DataFrame(lows).reindex(panel.index)[symbols]
print(f"highs/lows panels: {H.shape} {L.shape}  NaN highs: {int(H.isna().sum().sum())}")
print()

# ---- liveness diagnostic ----------------------------------------------------
print("=" * 78)
print("SIGNAL LIVENESS  (fraction of symbol-days flagged long)")
print("=" * 78)
print(f"{'variant':<22}{'p':>4}{'lower':>7}{'pers':>6}"
      f"{'TRAIN %sym-days':>17}{'TEST %sym-days':>16}{'TEST names/reb':>17}"
      f"{'TEST %dates>=8':>16}")

for label, period, lower, pers in [
    ("V1 canonical-state", 14, -80.0, None),
    ("V2 canonical-touch21", 14, -80.0, 21),
    ("V3 deep-touch21", 14, -90.0, 21),
    ("V4 fast-touch21", 5, -80.0, 21),
    ("V5 slow-touch21", 28, -80.0, 21),
]:
    sig = signal_panel(panel, H, L, period, lower, pers)
    tr = sig.loc[: str(TRAIN[1].date())]
    te = sig.loc[str(TEST[0].date()):]
    n_tr = int((tr > 0).sum().sum())
    n_te = int((te > 0).sum().sum())
    cnt = te.sum(axis=1)
    rb = cnt[cnt > 0]
    print(f"{label:<22}{period:>4}{lower:>7.0f}{str(pers):>6}"
          f"{100 * n_tr / tr.size:>16.2f}%{100 * n_te / te.size:>15.2f}%"
          f"{float(rb.mean()) if len(rb) else 0.0:>17.1f}"
          f"{100 * float((cnt >= 8).mean()):>15.1f}%")

print()
print("NOTE: 'names/reb' is the mean count of flagged names on days that have any.")
print("A book that needs >=22 names to fill is fully invested; one that flags 3 is")
print("a 3-name concentrated book, not an equal-weight index bet.")
print()

# ---- how many names available at the monthly rebalance dates specifically ------
from nsealgo.backtest.engine import _rebalance_dates  # noqa: E402

rb = _rebalance_dates(panel.index, "M")[1:]
print("=" * 78)
print("FLAG COUNT ON MONTHLY REBALANCE DATES ONLY (this is what the engine sees)")
print("=" * 78)
for label, period, lower, pers in [
    ("V1 canonical-state", 14, -80.0, None),
    ("V2 canonical-touch21", 14, -80.0, 21),
    ("V3 deep-touch21", 14, -90.0, 21),
    ("V4 fast-touch21", 5, -80.0, 21),
    ("V5 slow-touch21", 28, -80.0, 21),
]:
    sig = signal_panel(panel, H, L, period, lower, pers)
    c = sig.loc[rb].sum(axis=1)
    ctr = c.loc[: str(TRAIN[1].date())]
    cte = c.loc[str(TEST[0].date()):]
    print(f"{label:<22} TRAIN mean {ctr.mean():>5.1f} median {ctr.median():>5.1f} "
          f"zero-dates {100 * float((ctr == 0).mean()):>5.1f}%   |   "
          f"TEST mean {cte.mean():>5.1f} median {cte.median():>5.1f} "
          f"zero-dates {100 * float((cte == 0).mean()):>5.1f}%")
