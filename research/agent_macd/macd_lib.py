"""MACD signal reproduction, vectorised, prefix-stable, bit-compatible with the catalog.

The catalog lives in `src/cryptobot/strategies/indicators.py`:

    macd(closes, fast, slow)            -> ema(closes, fast) - ema(closes, slow)
    macd_signal(closes, fast, slow, sig) -> mean(macd_line[-sig:])

where `ema` is the recursion seeded at bar 0:  out = k*x + (1-k)*out.

Because that recursion is *prefix-stable* (the value after bar i depends only on bars
0..i), computing the whole series at once gives the identical series to calling the
scalar function on every prefix. `verify_against_catalog()` asserts this numerically
rather than assuming it.

Note on the signal line: the catalog uses a SIMPLE mean of the last `sig` MACD values,
not the textbook EMA signal line. This module reproduces the catalog exactly.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _ema_series(a: np.ndarray, period: int) -> np.ndarray:
    """`cryptobot.strategies.indicators._ema_series`, reproduced exactly."""
    k = 2.0 / (period + 1)
    out = np.empty(len(a), dtype=float)
    out[0] = a[0]
    for i in range(1, len(a)):
        out[i] = k * a[i] + (1 - k) * out[i - 1]
    return out


def macd_line(panel: pd.DataFrame, fast: int, slow: int) -> pd.DataFrame:
    """MACD line per symbol. NaN until bar `slow` (catalog guard: `len < slow -> NaN`).

    The catalog takes a contiguous list of closes; a NaN would poison the recursion
    permanently, so each column is run over its contiguous valid span.
    """
    out = pd.DataFrame(np.nan, index=panel.index, columns=panel.columns)
    for c in panel.columns:
        a = panel[c].to_numpy(dtype=float)
        mask = ~np.isnan(a)
        if int(mask.sum()) < slow:
            continue
        a = a[mask]
        line = _ema_series(a, fast) - _ema_series(a, slow)
        out.loc[panel.index[mask], c] = line
    return out


def macd_signal_line(panel: pd.DataFrame, fast: int, slow: int, sig: int) -> pd.DataFrame:
    """Catalog `macd_signal`: mean of the last `sig` MACD-line values.

    NaN until bar `slow + sig`, matching the catalog guard `len < slow + sig -> NaN`.
    """
    out = pd.DataFrame(np.nan, index=panel.index, columns=panel.columns)
    for c in panel.columns:
        a = panel[c].to_numpy(dtype=float)
        mask = ~np.isnan(a)
        if int(mask.sum()) < slow + sig:
            continue
        a = a[mask]
        line = (_ema_series(a, fast) - _ema_series(a, slow))[slow:]
        roll = np.full(len(a), np.nan)
        start = slow + sig - 1
        for i in range(start, len(roll)):
            roll[i] = line[i - start : i - start + sig].mean()
        out.loc[panel.index[mask], c] = roll
    return out


def signal_state(panel: pd.DataFrame, fast: int, slow: int, sig: int) -> pd.DataFrame:
    """+1 / 0 / -1 exactly as `MacdStrategy.signal` returns it.

    Catalog guard, transcribed: NaN on either side, or exact tie -> 0.
    """
    line = macd_line(panel, fast, slow)
    sl = macd_signal_line(panel, fast, slow, sig)
    good = line.notna() & sl.notna() & (line != sl)
    st = pd.DataFrame(0.0, index=panel.index, columns=panel.columns)
    st[good & (line > sl)] = 1.0
    st[good & (line < sl)] = -1.0
    return st


def score_from_signal(panel: pd.DataFrame, st: pd.DataFrame, mom_days: int = 126) -> pd.DataFrame:
    """Brief §5 recipe: rank trailing momentum only among names flagged long."""
    mom = panel / panel.shift(mom_days) - 1.0
    return mom.where(st > 0).rank(axis=1, pct=True)


# --------------------------------------------------------------------------- #
# Numerical verification against the actual catalog code
# --------------------------------------------------------------------------- #


def verify_against_catalog(
    panel: pd.DataFrame, symbols: list[str], params: list[tuple[int, int, int]]
) -> dict:
    """Compare the vectorised signal against the literal catalog call, bar by bar.

    Runs the real `MacdStrategy.signal()` on every rolling prefix of a few symbols and
    checks the vectorised series agrees: identical values everywhere the catalog returns
    a number, and NaN exactly over the warmup prefix where the catalog returns NaN.
    O(n^2) per symbol, so deliberately bounded.
    """
    from cryptobot.strategies.catalog.macd_strategy import MacdConfig, MacdStrategy

    out: dict = {}
    for fast, slow, sig in params:
        strat = MacdStrategy(MacdConfig(fast=fast, slow=slow, signal=sig))
        worst = 0.0
        nan_mismatch = 0
        for sym in symbols:
            closes = panel[sym].dropna().iloc[:700]
            arr = list(closes.to_numpy(dtype=float))
            got = np.array(
                [
                    float(strat.signal(arr[: i + 1], arr[: i + 1], arr[: i + 1], arr[: i + 1]))
                    for i in range(len(arr))
                ]
            )
            vec = signal_state(closes.to_frame(sym), fast, slow, sig)[sym].to_numpy(dtype=float)
            num = ~np.isnan(got)
            worst = max(worst, float(np.abs(got[num] - vec[num]).max()))
            # Where the catalog returns NaN, the vectorised version must be 0 or NaN
            # (0 = the catalog's own NaN->0 guard fires downstream). A *finite nonzero*
            # there would mean we invented a signal the catalog never produced.
            bad = ~num & ~np.isnan(vec) & (vec != 0.0)
            nan_mismatch += int(bad.sum())
        out[f"{fast}/{slow}/{sig}"] = {
            "max_abs_diff_on_defined_bars": worst,
            "invented_signal_bars": nan_mismatch,
        }
    return out
