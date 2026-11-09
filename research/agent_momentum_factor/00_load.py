"""00 — mandatory data audit (brief §2). Run first, always."""

from __future__ import annotations

import common
import pandas as pd

panel, symbols, report = common.load_panel()

print(report.describe())
print(f"symbols        : {len(symbols)}")
print(f"panel shape    : {panel.shape}")
print(f"index          : {panel.index[0].date()} -> {panel.index[-1].date()} "
      f"{panel.index.tz}")
print(f"NaN cells      : {int(panel.isna().sum().sum())}")

for label, s, e in (
    ("TRAIN", common.TRAIN_START, common.TRAIN_END),
    ("TEST", common.TEST_START, common.TEST_END),
):
    m = (panel.index >= s) & (panel.index <= e)
    sub = panel.loc[m]
    print(f"{label:6s} bars   : {len(sub)}  ({sub.index[0].date()} -> "
          f"{sub.index[-1].date()})")

eq = panel.pct_change(fill_method=None).mean(axis=1)
for label, s, e in (
    ("TRAIN", common.TRAIN_START, common.TRAIN_END),
    ("TEST", common.TEST_START, common.TEST_END),
):
    w = eq.loc[(eq.index >= s) & (eq.index <= e)]
    yrs = len(w) / 244
    print(f"{label:6s} equal-weight CAGR %: {(1 + w).prod() ** (1 / yrs) * 100 - 100:.2f}")

# Per-symbol history start, to expose the short-history names in the backfilled panel.
starts = panel.apply(lambda c: c.first_valid_index())
cut = pd.Timestamp("2022-01-01", tz="Asia/Kolkata")
early = starts[starts > cut]
print(f"\nsymbols whose history starts after {cut.date()} ({len(early)}):")
for sym, dt in early.items():
    print(f"  {sym:14s} first valid close {dt.date()}")
