"""Shared data prep for the atr_breakout agent.

Builds the wide OHLC panels once and caches them to parquet so every subsequent
script is fast and identical. All panels are tz-aware (Asia/Kolkata) daily bars,
cleaned by `nsealgo.data.loader` (C1-C7).

The ATR breakout signal needs high/low/close, but `load_universe` only returns the
close panel — so OHLC is loaded per symbol with the same `load_symbol` cleaning path.
"""

from __future__ import annotations

import os
import sys

import pandas as pd

sys.path.insert(0, "src")

from nsealgo.data.loader import EXCLUDE_SYMBOLS, load_symbol  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "ohlc.pkl")
DATA = "data/nse"


def build(data_dir: str = DATA):
    """Return (open, high, low, close, symbols) wide panels."""
    frames: dict[str, pd.DataFrame] = {}
    for fname in sorted(os.listdir(data_dir)):
        if not fname.endswith("_1d.csv"):
            continue
        symbol = fname[: -len("_1d.csv")]
        if symbol in EXCLUDE_SYMBOLS:
            continue
        df = load_symbol(os.path.join(data_dir, fname), symbol)
        if len(df) < 1000:
            continue
        frames[symbol] = df[["open", "high", "low", "close"]]
    cols = sorted(frames)
    wide = {k: pd.DataFrame({c: frames[c][k] for c in cols}).sort_index() for k in
            ("open", "high", "low", "close")}
    return wide["open"], wide["high"], wide["low"], wide["close"], cols


def load(data_dir: str = DATA):
    """Cached variant of :func:`build`."""
    if os.path.exists(CACHE):
        return pd.read_pickle(CACHE)
    out = build(data_dir)
    pd.to_pickle(out, CACHE)
    return out


if __name__ == "__main__":
    o, h, lo, c, syms = load()
    print(f"symbols={len(syms)}")
    print(f"index  {c.index[0].date()} -> {c.index[-1].date()}  n={len(c)}")
    print(f"close shape {c.shape}")
    nan_frac = float(c.isna().mean().mean())
    print(f"close NaN fraction (whole panel, before any fill): {nan_frac:.4%}")
    for name, p in (("open", o), ("high", h), ("low", lo), ("close", c)):
        assert (p.dropna(how="all").index == c.dropna(how="all").index).all(), name
    print("index alignment OK across open/high/low/close")
