"""Data loading and strict TRAIN/TEST isolation.

The optimiser must never see TEST. That is enforced here structurally rather than by
convention: :func:`train_bars` is the only thing the search loop is handed, and TEST is
produced by a separate call that the search loop never receives.

We learned this the hard way. ``research/validate.py`` ran its negative control over the
full 2008-2026 panel and printed "PASS" on an in-sample comparison that reversed
out-of-sample. Structural isolation is the fix; a comment asking people to be careful is
not.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import config as C

log = logging.getLogger(__name__)

_CACHE: dict[str, pd.DataFrame] = {}


@dataclass(frozen=True)
class Window:
    start: str
    end: str


TRAIN = Window(C.TRAIN_START, C.TRAIN_END)
TEST = Window(C.TEST_START, C.TEST_END)
FULL = Window(C.CLEAN_START, C.TEST_END)


def _read(sym: str, timeframe: str = "1d") -> pd.DataFrame:
    """Read one symbol's daily OHLCV with the same cleaning rules the main loader uses.

    Only the rules that matter for single-stock bars are applied (non-positive prices,
    duplicate timestamps, frozen feeds). The full rule set lives in
    ``nsealgo.data.loader`` and is exercised by the production engine; re-implementing it
    here would risk drift, so the shared loader is used for the panel and this reads the
    per-symbol file for the streaming backtest.
    """
    key = f"{sym}:{timeframe}"
    if key in _CACHE:
        return _CACHE[key]

    path = C.DATA_DIR / f"{sym}_{timeframe}.csv"
    if not path.exists():
        _CACHE[key] = pd.DataFrame()
        return _CACHE[key]

    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]

    tcol = next((c for c in ("date", "datetime", "ts", "timestamp") if c in df.columns), None)
    if tcol is None:
        raise KeyError(f"{path.name}: no date column in {list(df.columns)}")

    # The panel stores epoch **milliseconds** (``ts`` column), matching nsealgo's loader.
    # ``pd.to_datetime`` on bare ints assumes *seconds*, which lands in 1970 and silently
    # empties every slice -- so the unit must be stated explicitly.
    if pd.api.types.is_numeric_dtype(df[tcol]):
        idx = pd.to_datetime(df[tcol], unit="ms", utc=True, errors="coerce")
    else:
        idx = pd.to_datetime(df[tcol], utc=True, errors="coerce")

    df = df.assign(_ts=idx).dropna(subset=["_ts"]).set_index("_ts")
    df.index = df.index.tz_convert("Asia/Kolkata").tz_localize(None).normalize()
    df = df[~df.index.duplicated(keep="last")].sort_index()

    for c in ("open", "high", "low", "close", "volume", "vol"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if "volume" not in df.columns and "vol" in df.columns:
        df = df.rename(columns={"vol": "volume"})
    if "close" not in df.columns:
        raise KeyError(f"{path.name}: no close column")

    # C1 + C4: pre-2008 is unusable; non-positive prices are never forward-filled.
    df = df[df.index >= pd.Timestamp(C.CLEAN_START)]
    df = df[np.isfinite(df["close"]) & (df["close"] > 0)]
    if {"high", "low"}.issubset(df.columns):
        df = df[(df["high"] > 0) & (df["low"] > 0)]
    df = df[df["volume"].fillna(0) >= 0] if "volume" in df.columns else df

    # C9: drop vendor-feed freezes (runs of >=5 identical closes), matching the main loader.
    close = df["close"]
    run_id = (close != close.shift()).cumsum()
    run_len = close.groupby(run_id).transform("size")
    df = df[~(run_len >= 5)]

    keep = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    df = df[keep]
    _CACHE[key] = df
    return df


#: Symbols the production loader excludes for structural corruption of the source files
#: (``nsealgo.data.loader`` reports ``excluded symbols: ['adanient', 'jiofin']``). The
#: same exclusions are applied here so this sweep never optimises on data the production
#: engine has already rejected -- otherwise the two harnesses would silently disagree.
EXCLUDED_SYMBOLS = frozenset({"adanient", "jiofin"})


def available_symbols(timeframe: str = "1d", include_excluded: bool = False) -> list[str]:
    out = []
    for p in sorted(C.DATA_DIR.glob(f"*_{timeframe}.csv")):
        sym = p.name[: -len(f"_{timeframe}.csv")]
        if not include_excluded and sym in EXCLUDED_SYMBOLS:
            continue
        out.append(sym)
    return out


def bars(sym: str, window: Window = FULL, timeframe: str = "1d") -> pd.DataFrame:
    df = _read(sym, timeframe)
    if df.empty:
        return df
    return df[(df.index >= pd.Timestamp(window.start)) & (df.index <= pd.Timestamp(window.end))]


def train_bars(sym: str, timeframe: str = "1d") -> pd.DataFrame:
    """The ONLY window the parameter search may see."""
    return bars(sym, TRAIN, timeframe)


def test_bars(sym: str, timeframe: str = "1d") -> pd.DataFrame:
    """Held out. Produced separately, opened once, after the config is frozen."""
    return bars(sym, TEST, timeframe)
