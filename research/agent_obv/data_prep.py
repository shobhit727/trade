"""Shared data prep for the on_balance_volume agent.

Builds and caches:
  * close panel (via `nsealgo.data.loader.load_universe`)
  * volume panel (via `nsealgo.data.loader.load_symbol`, same cleaning rules)
  * TRAIN / TEST splits
  * OBV matrix + OBV-change matrix

`load_universe` returns only closes; OBV needs volume, so volume is loaded per symbol
through the *same* `load_symbol` cleaning path (C1-C6) rather than by a second, weaker
reader. Guarantees the two panels share identical cleaning semantics.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "src")

from nsealgo.data.loader import load_symbol, load_universe  # noqa: E402

DATA_DIR = "data/nse"
CACHE = "research/agent_obv/_cache"

TRAIN_START = pd.Timestamp("2016-01-01", tz="Asia/Kolkata")
TRAIN_END = pd.Timestamp("2023-12-31", tz="Asia/Kolkata")
TEST_START = pd.Timestamp("2024-01-01", tz="Asia/Kolkata")
TEST_END = pd.Timestamp("2026-10-01", tz="Asia/Kolkata")


def build() -> tuple[pd.DataFrame, pd.DataFrame, object, str]:
    os.makedirs(CACHE, exist_ok=True)
    panel, symbols, report = load_universe(DATA_DIR)

    # --- volume panel: same loader, same cleaning, one pass per symbol
    vols: dict[str, pd.Series] = {}
    for s in symbols:
        df = load_symbol(os.path.join(DATA_DIR, f"{s}_1d.csv"), s)
        if df.empty:
            continue
        vols[s] = df["vol"].rename(s)
    vol_panel = pd.DataFrame(vols).reindex(panel.index)

    report_str = report.describe()
    print(report_str)
    print(f"\nsymbols          : {len(symbols)}")
    print(f"panel            : {panel.shape[0]} rows x {panel.shape[1]} cols")
    print(f"panel span       : {panel.index.min().date()} -> {panel.index.max().date()}")
    print(f"vol panel        : {vol_panel.shape[0]} rows x {vol_panel.shape[1]} cols")
    nn = vol_panel.notna().mean().mean()
    print(f"vol coverage     : {nn * 100:.1f}% of symbol-days non-null")
    zero = (vol_panel.fillna(0) == 0).mean().mean()
    print(f"zero-volume days : {zero * 100:.2f}% of cells")

    panel.to_parquet(f"{CACHE}/panel.parquet")
    vol_panel.to_parquet(f"{CACHE}/vol_panel.parquet")
    return panel, vol_panel, report, report_str


def load():
    panel = pd.read_parquet(f"{CACHE}/panel.parquet")
    vol_panel = pd.read_parquet(f"{CACHE}/vol_panel.parquet")
    return panel, vol_panel


def obv_matrix(panel: pd.DataFrame, vol_panel: pd.DataFrame) -> pd.DataFrame:
    """Textbook OBV, per symbol, over that symbol's own clean history.

    obv[i] = obv[i-1] + sign(c[i]-c[i-1]) * vol[i]

    Computed on the forward-filled-from-the-past close series so that a one-day
    listing gap cannot silently reset the accumulator.
    """
    close = panel.ffill()
    vol = vol_panel.ffill()
    sign = np.sign(close.diff())
    step = sign * vol
    # OBV is a cumulative sum of the *signed volume* steps. First valid bar is
    # the first non-null step.
    return step.cumsum()


def obv_change(obv: pd.DataFrame, n: int) -> pd.DataFrame:
    """OBV change over `n` bars: obv(t) - obv(t-n). > 0 == accumulation."""
    return obv - obv.shift(n)


def split_train(df: pd.DataFrame) -> pd.DataFrame:
    return df.loc[(df.index >= TRAIN_START) & (df.index <= TRAIN_END)]


def split_test(df: pd.DataFrame) -> pd.DataFrame:
    return df.loc[(df.index >= TEST_START) & (df.index <= TEST_END)]


if __name__ == "__main__":
    build()
