"""Mandatory step: load_universe audit + OHLC rebuild for flag_pattern.

Run: .venv/bin/python research/agent_flag_pattern/s0_audit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from nsealgo.data.loader import CleaningReport, load_symbol, load_universe  # noqa: E402

DATA = str(ROOT / "data" / "nse")

panel, symbols, report = load_universe(DATA)

print("=== load_universe().describe() ===")
print(report.describe())

print("\n=== panel ===")
print(f"shape        : {panel.shape}")
print(f"index        : {panel.index.min().date()} -> {panel.index.max().date()}")
print(f"n bars       : {len(panel.index)}")
print(f"symbols      : {len(symbols)}")
print(f"dtypes       : {set(panel.dtypes.astype(str))}")
print(f"NaN total    : {int(panel.isna().sum().sum())}")
print(f"NaN frac     : {float(panel.isna().sum().sum()) / panel.size:.4%}")
print(f"min price    : {float(panel.min().min()):.4f}")
print(f"max price    : {float(panel.max().max()):.2f}")

# per-symbol start dates: the survivorship/backfill exposure
starts = panel.apply(lambda c: c.first_valid_index())
ends = panel.apply(lambda c: c.last_valid_index())
print("\n=== per-symbol coverage ===")
print(f"earliest start : {starts.min().date()}  ({starts.idxmin()})")
print(f"latest start   : {starts.max().date()}  ({starts.idxmax()})")
print(f"earliest end   : {ends.min().date()}")
print(f"latest end     : {ends.max().date()}")
print("\nsymbols starting AFTER 2016-01-01 (i.e. joining the TRAIN set late):")
TZ = panel.index.tz
late = starts[starts > pd.Timestamp("2016-01-01", tz=TZ)].sort_values()
print(late.dt.strftime("%Y-%m-%d").to_string() if len(late) else "  none")

# how many names are present on a typical day -> sanity for the 22-name book
cnt = panel.notna().sum(axis=1)
print("\n=== names present per day ===")
print(f"min  : {int(cnt.min())}")
print(f"median: {int(cnt.median())}")
print(f"max  : {int(cnt.max())}")
for d in ("2016-01-04", "2020-03-16", "2024-01-02", "2026-09-30"):
    if pd.Timestamp(d) in cnt.index:
        print(f"  {d}: {int(cnt.loc[d])} names")

# OHLC rebuild: flag_pattern only needs closes, but V3/V4 need highs.
print("\n=== OHLC rebuild (for V3/V4 breakout levels) ===")
closes, highs = {}, {}
for sym in symbols:
    df = load_symbol(str(Path(DATA) / f"{sym}_1d.csv"), sym, CleaningReport())
    closes[sym] = df["close"].rename(sym)
    highs[sym] = df["high"].rename(sym)
c = pd.DataFrame(closes).sort_index().dropna(how="all")
h = pd.DataFrame(highs).reindex(index=c.index, columns=c.columns)
print(f"close rebuild equals load_universe panel : {c.equals(panel)}")
print(f"close >= high on every bar (sanity)     : "
      f"{bool((c >= h).where(c.notna() & h.notna()).all().all())}")
print(f"high NaN frac                            : {float(h.isna().sum().sum()) / h.size:.4%}")

# The window actually used by the protocol
for label, lo, hi in (
    ("TRAIN", "2016-01-01", "2023-12-31"),
    ("TEST", "2024-01-01", "2026-10-01"),
):
    sub = panel.loc[lo:hi]
    print(f"\n{label} {lo}..{hi}: {sub.shape[0]} bars, "
          f"names/day min={int(sub.notna().sum(axis=1).min())} "
          f"med={int(sub.notna().sum(axis=1).median())}")

# persist for the other steps
out = Path(__file__).resolve().parent
c.to_pickle(out / "close.pkl")
h.to_pickle(out / "high.pkl")
panel.loc["2016-01-01":"2026-10-01"].to_pickle(out / "panel_proto.pkl")
print(f"\nwrote close.pkl / high.pkl / panel_proto.pkl to {out}")
