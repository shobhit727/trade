"""Vectorised Money Flow Index panel + a proof it equals the catalog implementation.

`cryptobot.strategies.indicators.mfi` is a scalar function over the trailing `period`
bars. It is O(n * period) per call and cannot be applied to a 48 x 4625 panel. This module
computes the same quantity with rolling sums, then **proves the two agree** by replaying
the catalog function over thousands of randomly chosen windows.

If the two ever disagree, `verify_against_catalog` raises. The whole run is downstream of
that check, so a silent indexing slip cannot reach a reported number.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "src")

from cryptobot.strategies.indicators import mfi as mfi_scalar  # noqa: E402


def mfi_panel(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame,
             vol: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Money Flow Index for every symbol, exactly as `indicators.mfi` defines it.

    The catalog function, at its final bar ``t``, sums the money flow of the **last
    ``period`` bars, *t* included**, each classified by the sign of ``tp[i] - tp[i-1]``.
    So the value at index *t* is a plain ``rolling(period)`` over *t-period+1 .. t* —
    **not** shifted back a bar. Deriving that window wrong is the classic MFI
    off-by-one, and it happened here on the first attempt; `verify_against_catalog`
    caught it (2313/2328 windows wrong) before any backtest ran. See REPORT.md bug B1.

    Degenerate cases are reproduced deliberately:
      * ``neg == 0``  -> ``100.0`` (catalog's explicit branch, not a division)
      * NaN anywhere in the window -> NaN (the catalog's running sum goes NaN too)
    """
    tp = (high + low + close) / 3.0
    d = tp.diff()
    flow = tp * vol
    # `.where(cond, 0.0)` keeps the value when the condition holds and zeroes it
    # otherwise — identical to the catalog's `if/elif`, which adds nothing on ties.
    # A bar whose typical price has no predecessor, or whose volume is missing, cannot
    # form a flow at all; the catalog would leave the running sum NaN there, so the
    # NaN must be preserved rather than silently zero-filled.
    valid = d.notna() & flow.notna()
    pos = flow.where(d > 0, 0.0).where(valid, np.nan)
    neg = flow.where(d < 0, 0.0).where(valid, np.nan)

    pos_sum = pos.rolling(period, min_periods=period).sum()
    neg_sum = neg.rolling(period, min_periods=period).sum()

    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = pos_sum / neg_sum
        out = 100.0 - 100.0 / (1.0 + ratio)
    return out.where(neg_sum != 0, 100.0)


def verify_against_catalog(high, low, close, vol, period: int = 14,
                           n_windows: int = 3000, seed: int = 7) -> dict:
    """Replay `indicators.mfi` over random windows and require exact agreement."""
    rng = np.random.default_rng(seed)
    n_bars = len(close)
    syms = list(close.columns)
    need = period + 1

    checked = 0
    nans = 0
    max_abs_diff = 0.0
    mismatches: list[tuple] = []

    for _ in range(n_windows):
        sym = syms[rng.integers(len(syms))]
        end = int(rng.integers(need, n_bars))
        c = close[sym].iloc[end - need : end + 1].to_numpy(float)
        h = high[sym].iloc[end - need : end + 1].to_numpy(float)
        lo = low[sym].iloc[end - need : end + 1].to_numpy(float)
        v = vol[sym].iloc[end - need : end + 1].to_numpy(float)
        if not np.isfinite(c).all():
            continue
        ref = mfi_scalar(c, h, lo, v, period)
        got = mfi_panel(
            high[[sym]], low[[sym]], close[[sym]], vol[[sym]], period
        )[sym].iloc[end]
        checked += 1
        if np.isnan(ref):
            nans += 1
            if not np.isnan(got):
                mismatches.append((sym, str(close.index[end].date()), ref, got))
            continue
        if np.isnan(got):
            mismatches.append((sym, str(close.index[end].date()), ref, got))
            continue
        d = abs(ref - got)
        if d > max_abs_diff:
            max_abs_diff = float(d)
        if d > 1e-9:
            mismatches.append((sym, str(close.index[end].date()), ref, got))

    if mismatches:
        raise AssertionError(
            f"vectorised MFI disagrees with catalog on {len(mismatches)}/{checked} "
            f"windows, e.g. {mismatches[:5]}"
        )
    return {
        "period": period,
        "windows_checked": checked,
        "nan_windows": nans,
        "max_abs_diff": max_abs_diff,
    }


def signal_panel(mfi: pd.DataFrame, lower: float) -> pd.DataFrame:
    """`MfiStrategy.signal()` == +1 branch only.

    The `-1` branch (mfi > upper) is dropped: a long-only Indian delivery book cannot
    take a short, so in this mandate it is a no-op by construction, not a filter.
    """
    return (mfi < lower).astype(float)


def mfi_stats(mfi: pd.DataFrame, train_end: pd.Timestamp) -> pd.Series:
    """Distribution of the raw oscillator, on the TRAIN window only."""
    s = mfi.loc[:train_end].stack()
    return s.describe(percentiles=[0.001, 0.005, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95])


def liveness(sig: pd.DataFrame, index: pd.DatetimeIndex) -> dict:
    """Fraction of symbol-days flagged long, and names long per day."""
    sub = sig.loc[index]
    per_day = sub.sum(axis=1)
    return {
        "frac_symbol_days_long": float(sub.to_numpy().mean()),
        "mean_names_long": float(per_day.mean()),
        "median_names_long": float(per_day.median()),
        "min_names_long": float(per_day.min()),
        "p05_names_long": float(per_day.quantile(0.05)),
        "days_with_zero_names": int((per_day == 0).sum()),
        "days_with_lt_5_names": int((per_day < 5).sum()),
        "days_total": int(len(per_day)),
    }
