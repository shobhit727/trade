"""Data preparation for the MFI agent run.

`nsealgo.data.loader.load_universe` returns a **close panel only**. The Money Flow Index
needs `high`, `low` and `vol`, so this module rebuilds those panels by calling the *same*
`load_symbol` used by `load_universe` — identical C1-C9 cleaning, identical exclusions,
identical `min_bars` — and then re-indexes them onto the audited close panel so the traded
price series is byte-identical to the one every other agent backtests.

The equality of the close columns to `load_universe`'s is asserted in `verify()`; if a
future loader edit changes the cleaning, this harness fails loudly rather than silently
backtesting on a different panel than everyone else.
"""

from __future__ import annotations

import os
import sys

import pandas as pd

sys.path.insert(0, "src")

from nsealgo.data.loader import (  # noqa: E402
    EXCLUDE_SYMBOLS,
    CleaningReport,
    load_symbol,
    load_universe,
)

DATA_DIR = os.environ.get("NSE_DATA", "data/nse")

TRAIN_START = pd.Timestamp("2016-01-01", tz="Asia/Kolkata")
TRAIN_END = pd.Timestamp("2023-12-31", tz="Asia/Kolkata")
TEST_START = pd.Timestamp("2024-01-01", tz="Asia/Kolkata")
TEST_END = pd.Timestamp("2026-10-01", tz="Asia/Kolkata")


def load_ohlcv(data_dir: str = DATA_DIR) -> tuple[pd.DataFrame, ...]:
    """Return (close, high, low, vol) panels built by the audited loader path.

    Mirrors `load_universe`'s own symbol selection: same exclusion set, same
    `min_bars=1000`, same `DataIntegrityError` -> drop behaviour.
    """
    close_s: dict[str, pd.Series] = {}
    high_s: dict[str, pd.Series] = {}
    low_s: dict[str, pd.Series] = {}
    vol_s: dict[str, pd.Series] = {}
    dropped: list[str] = []

    for fname in sorted(os.listdir(data_dir)):
        if not fname.endswith("_1d.csv"):
            continue
        symbol = fname[: -len("_1d.csv")]
        if symbol in EXCLUDE_SYMBOLS:
            dropped.append(symbol)
            continue
        local = CleaningReport()
        try:
            df = load_symbol(os.path.join(data_dir, fname), symbol, local)
        except Exception:  # noqa: BLE001 — same contract as load_universe
            dropped.append(symbol)
            continue
        if len(df) < 1000:
            dropped.append(symbol)
            continue
        close_s[symbol] = df["close"].rename(symbol)
        high_s[symbol] = df["high"].rename(symbol)
        low_s[symbol] = df["low"].rename(symbol)
        vol_s[symbol] = df["vol"].rename(symbol)

    def _frame(d: dict[str, pd.Series]) -> pd.DataFrame:
        return pd.DataFrame(d).sort_index()

    return _frame(close_s), _frame(high_s), _frame(low_s), _frame(vol_s), dropped


def load_all(data_dir: str = DATA_DIR):
    """Close panel from `load_universe` + OHLCV panels + the audited cleaning report."""
    panel, symbols, report = load_universe(data_dir)
    close, high, low, vol, dropped = load_ohlcv(data_dir)
    return panel, symbols, report, close, high, low, vol, dropped


def verify(panel: pd.DataFrame, close: pd.DataFrame, high, low, vol) -> dict:
    """Assert the harness is backtesting the same panel everyone else is."""
    assert list(close.columns) == sorted(close.columns)
    if set(close.columns) != set(panel.columns):
        missing = set(panel.columns) ^ set(close.columns)
        raise AssertionError(f"symbol mismatch vs load_universe: {sorted(missing)}")

    idx = panel.index
    close_a = close.reindex(index=idx, columns=panel.columns)
    diff = (close_a - panel).abs()
    nan_mismatch = int((close_a.isna() != panel.isna()).sum().sum())
    if nan_mismatch:
        raise AssertionError(f"{nan_mismatch} NaN-pattern mismatches vs load_universe")
    maxdiff = float(np.nanmax(diff.values)) if not diff.empty else 0.0
    if maxdiff > 0:
        raise AssertionError(f"close panel differs from load_universe by {maxdiff}")

    hv = high.reindex(index=idx, columns=panel.columns)
    lv = low.reindex(index=idx, columns=panel.columns)
    vv = vol.reindex(index=idx, columns=panel.columns)
    return {
        "max_close_diff": maxdiff,
        "symbols": len(panel.columns),
        "bars": len(idx),
        "start": str(idx[0].date()),
        "end": str(idx[-1].date()),
        "high_nan_pct": float(hv.isna().mean().mean() * 100),
        "low_nan_pct": float(lv.isna().mean().mean() * 100),
        "vol_nan_pct": float(vv.isna().mean().mean() * 100),
        "vol_zero_pct": float((vv.fillna(np.nan) == 0).mean().mean() * 100),
        "h_ge_c_pct": float((hv >= close_a).mean().mean() * 100),
        "l_le_c_pct": float((lv <= close_a).mean().mean() * 100),
        "l_le_h_pct": float((lv <= hv).mean().mean() * 100),
    }


import numpy as np  # noqa: E402  (imported late; only used in verify)

if __name__ == "__main__":
    import json

    from nsealgo.provenance import provenance

    panel, symbols, report, close, high, low, vol, dropped = load_all()
    print(json.dumps(provenance(), indent=2))
    print(report.describe())
    print("symbols dropped by symbol-selection:", dropped)
    stats = verify(panel, close, high, low, vol)
    print(json.dumps(stats, indent=2))
