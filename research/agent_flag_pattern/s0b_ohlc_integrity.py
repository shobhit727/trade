"""OHLC integrity audit — CORRECT invariants this time.

My first audit asserted ``close >= high`` which is backwards: in real OHLC the close is
normally BELOW the session high, so ``close <= high`` is the invariant. That was my
script's bug, not the data's. This file checks the right way and validates against the
raw CSVs so a panel-build error cannot hide.

Run: .venv/bin/python research/agent_flag_pattern/s0b_ohlc_integrity.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

HERE = Path(__file__).resolve().parent
DATA = ROOT / "data" / "nse"

c = pd.read_pickle(HERE / "close.pkl")
h = pd.read_pickle(HERE / "high.pkl")


def check(name, mask_ok, mask_bad, total):
    nbad = int(mask_bad.sum().sum())
    print(f"  {name:<28} violations {nbad:>7d} / {int(total.sum().sum()):>7d}"
          f"  ({nbad / max(int(total.sum().sum()), 1):.4%})")
    return nbad


print("=== OHLC invariants on the rebuilt panels (correct direction) ===")
valid = c.notna() & h.notna()
check("close <= high", valid & (c <= h), valid & (c > h), valid)

# Full OHLC, straight from the raw CSVs, all four columns.
frames = {}
for sym in c.columns:
    df = pd.read_csv(DATA / f"{sym}_1d.csv")
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True).dt.tz_convert(
        "Asia/Kolkata")
    # the cleaner normalises session timestamps to session midnight
    frames[sym] = df.set_index("ts").sort_index().rename_axis("ts")
    frames[sym].index = frames[sym].index.normalize()

print("\n=== full 4-column OHLC invariants (raw csv -> cleaning) ===")
tot = 0
tot_ok = 0
worst = []
for sym, df in frames.items():
    d = df.loc["2016-01-01":"2026-10-01"]
    d = d.replace([np.inf, -np.inf], np.nan)
    o, hi, lo, cl = d["open"], d["high"], d["low"], d["close"]
    ok = o.notna() & hi.notna() & lo.notna() & cl.notna()
    tot_ok += int(ok.sum().sum())
    for nm, cond in (
        ("low <= open", lo <= o),
        ("low <= close", lo <= cl),
        ("low <= high", lo <= hi),
        ("open <= high", o <= hi),
        ("close <= high", cl <= hi),
        ("all prices > 0", (o > 0) & (hi > 0) & (lo > 0) & (cl > 0)),
    ):
        v = int((ok & ~cond.fillna(True)).sum().sum())
        tot += v
        if v:
            worst.append((nm, sym, v))
print(f"  total OHLC invariant violations : {tot} / {tot_ok} bar-cells")

print("\n=== gap check: does high always exceed close? (needed for breakout logic) ===")
gap = ((h - c) / c).where(valid)
print(gap.stack().describe(percentiles=[0.01, 0.5, 0.99]).to_string())
print(f"  bars with high == close exactly : "
      f"{int((valid & (h == c)).sum().sum())} "
      f"({float((valid & (h == c)).sum().sum()) / max(int(valid.sum().sum()), 1):.3%})")

print("\n=== the 3 largest intraday ranges in the TEST window ===")
rng = ((h - c) / c).where(valid).loc["2024-01-01":]
st = rng.stack().sort_values(ascending=False).head(3)
# stack() yields (date, symbol): level 0 is the original row index.
for (dt, sym), v in st.items():
    d = frames[sym].loc[dt.normalize()]
    print(f"  {sym} {dt.strftime('%Y-%m-%d')}: "
          f"range {v:.2%}  O={d['open']:.2f} H={d['high']:.2f} "
          f"L={d['low']:.2f} C={d['close']:.2f}")
