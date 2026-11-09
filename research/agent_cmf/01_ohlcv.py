"""Step 01 — build OHLCV + CMF panels for the universe.

CMF (Chaikin Money Flow) = sum(MFM * vol) / sum(vol) over `period` bars, where
MFM = ((C-L) - (H-C)) / (H-L).  This mirrors `cryptobot.strategies.indicators.chaikin_mf`
exactly, but vectorised and point-in-time (window ends at t, no lookahead).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, "src")

import numpy as np
import pandas as pd

from nsealgo.data.loader import EXCLUDE_SYMBOLS, DataIntegrityError, load_symbol

DATA = "data/nse"


def build_ohlcv(data_dir: str = DATA) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for fname in sorted(os.listdir(data_dir)):
        if not fname.endswith("_1d.csv"):
            continue
        sym = fname[: -len("_1d.csv")]
        if sym in EXCLUDE_SYMBOLS:
            continue
        try:
            df = load_symbol(os.path.join(data_dir, fname), sym)
        except DataIntegrityError:
            continue
        if len(df) < 1000:
            continue
        frames[sym] = df
    return frames


def cmf_panel(
    closes: pd.DataFrame,
    highs: pd.DataFrame,
    lows: pd.DataFrame,
    vols: pd.DataFrame,
    period: int = 20,
) -> pd.DataFrame:
    """Rolling volume-weighted MFM. NaN where any input is missing."""
    rng = (highs - lows).replace(0.0, np.nan)
    mfm = ((closes - lows) - (highs - closes)) / rng
    num = (mfm * vols).rolling(period, min_periods=period).sum()
    den = vols.rolling(period, min_periods=period).sum()
    out = num / den.replace(0.0, np.nan)
    return out.where(rng.notna() | highs.isna())


if __name__ == "__main__":
    frames = build_ohlcv()
    print("symbols with OHLCV:", len(frames))
    syms = sorted(frames)
    idx = None
    for s in syms:
        f = frames[s]
        idx = f.index if idx is None else idx.union(f.index)
    idx = idx.sort_values()

    closes = pd.DataFrame({s: frames[s]["close"] for s in syms}).reindex(idx)
    highs = pd.DataFrame({s: frames[s]["high"] for s in syms}).reindex(idx)
    lows = pd.DataFrame({s: frames[s]["low"] for s in syms}).reindex(idx)
    vols = pd.DataFrame({s: frames[s]["vol"] for s in syms}).reindex(idx)

    print("index:", len(idx), idx[0], "->", idx[-1])
    print("NaN per panel:")
    for nm, p in [("close", closes), ("high", highs), ("low", lows), ("vol", vols)]:
        print(f"  {nm:6s} {int(p.isna().sum().sum()):>8,}  "
              f"symbols w/ any NaN: {int((p.isna().sum() > 0).sum())}")

    # Parity check against the catalog implementation on one symbol.
    sys.path.insert(0, "src")
    from cryptobot.strategies.indicators import chaikin_mf

    s = syms[0]
    c = closes[s].dropna()
    h = highs[s].reindex(c.index)
    lo = lows[s].reindex(c.index)
    v = vols[s].reindex(c.index)
    # The catalog indicator indexes positionally, so hand it numpy arrays.
    ca, ha, la, va = (x.to_numpy(dtype=float) for x in (c, h, lo, v))
    for period in (20, 60):
        mine = cmf_panel(
            closes[[s]], highs[[s]], lows[[s]], vols[[s]], period
        )[s].reindex(c.index)
        ref = pd.Series(
            [chaikin_mf(ca[:i], ha[:i], la[:i], va[:i], period)
             for i in range(period, len(ca) + 1)],
            index=c.index[period - 1:],
        )
        both = pd.concat([mine.rename("mine"), ref.rename("ref")], axis=1).dropna()
        diff = (both["mine"] - both["ref"]).abs().max()
        print(f"  parity {s} period={period}: max|diff| = {diff:.3e}  n={len(both)}")
        print(f"    mine range [{mine.min():.4f},{mine.max():.4f}]  "
              f"ref range [{ref.min():.4f},{ref.max():.4f}]")

    closes.to_pickle("research/agent_cmf/_closes.pkl")
    highs.to_pickle("research/agent_cmf/_highs.pkl")
    lows.to_pickle("research/agent_cmf/_lows.pkl")
    vols.to_pickle("research/agent_cmf/_vols.pkl")
    print("saved OHLCV panels")
