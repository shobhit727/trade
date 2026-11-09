"""Step 0 — mandatory universe load + report. No strategy logic yet."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from nsealgo.data.loader import load_universe  # noqa: E402

panel, symbols, report = load_universe(str(ROOT / "data" / "nse"))
print(report.describe())
print(f"\n{len(symbols)} symbols | {panel.index[0].date()} -> {panel.index[-1].date()} "
      f"| {len(panel)} bars | {len(panel)/244:.2f}y")
print(f"columns: {list(panel.columns)}")
print(f"index tz: {panel.index.tz}  dtype: {panel.index.dtype}")

# TRAIN / TEST split audit
tr = panel.loc["2016-01-01":"2023-12-31"]
te = panel.loc["2024-01-01":"2026-10-01"]
print(f"\nTRAIN {tr.index[0].date()} -> {tr.index[-1].date()}  {len(tr)} bars  "
      f"{len(tr)/244:.2f}y  names {tr.notna().sum().min()}-{tr.notna().sum().max()}")
print(f"TEST  {te.index[0].date()} -> {te.index[-1].date()}  {len(te)} bars  "
      f"{len(te)/244:.2f}y  names {te.notna().sum().min()}-{te.notna().sum().max()}")
print("\nNaN fraction by year (last 6):")
print((panel.isna().mean(axis=1).groupby(panel.index.year).mean() * 100).tail(8).round(2).to_string())
