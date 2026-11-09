"""Wave 1 / agent 14 -- Regime A: REALISED SKEW OF INTRADAY RANGES.

Hypothesis family: the *shape* of a name's daily high-low range distribution,
not its level. The harness already owns the level (low_vol, downside_vol,
vol_of_vol) and the position (high_52w, range_pos). What it does not own is
the ASYMMETRY of the range distribution: whether a name's typical trading day
is calm with occasional explosions (right-skewed) or frantic with occasional
lulls (left-skewed).

Mechanism (falsifiable, two-sided):
  * M1 -- JUMP-RISK PREMIUM. A right-skewed range distribution means the name
    takes occasional jump sessions. Jump risk is priced (Bates 2016; Barunik
    et al.), so those names should earn COMPENSATION: higher asymmetry ->
    higher forward return. This is the primary sign hypothesis.
  * M2 -- FRAGILITY / QUALITY. The same names are speculative, retail-driven
    and crash together; India's long-only record rewards low volatility, so
    higher asymmetry -> lower forward return. Tested by the registered
    negation of the primary factor.

Neither hypothesis is assumed; the sign is measured.

The range is ``log(high/low)`` -- the Parkinson/Garman-Klass style intraday
range, scale-free and drift-free, computed from the SHARED CLEANED OHLC
loader (``harness.ohlc_wide``) so the high/low used here cannot disagree with
the close panel the engine trades on.

All factors are trailing-window functions of bars up to and including the
current one: no lookahead, no centred windows.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.sweep.harness import factor, ohlc_wide

_RANGE_CACHE: dict[tuple, pd.DataFrame] = {}


def _log_range(px: pd.DataFrame) -> pd.DataFrame:
    """Daily log range log(high/low) on the panel's index and columns.

    Cached on the panel's identity because the harness recomputes the factor
    once per cell (36 cells per factor) and the rolling statistics below are
    the expensive part.
    """
    key = (px.index[0], px.index[-1], px.shape, tuple(px.columns))
    hit = _RANGE_CACHE.get(key)
    if hit is not None:
        return hit
    hi = ohlc_wide("high").reindex(index=px.index, columns=px.columns)
    lo = ohlc_wide("low").reindex(index=px.index, columns=px.columns)
    rng = np.log(hi / lo)
    _RANGE_CACHE[key] = rng
    return rng


def _safe_div(num: pd.DataFrame, den: pd.DataFrame) -> pd.DataFrame:
    return num / den.replace(0.0, np.nan)


@factor("rngskew_63")
def _rngskew_63(px: pd.DataFrame) -> pd.DataFrame:
    """Moment skewness of the 63-day daily log-range. Higher = more explosive
    right tail = jump-risk premium = higher forward return (M1)."""
    return _log_range(px).rolling(63, min_periods=30).skew()


@factor("rngskew_63_neg")
def _rngskew_63_neg(px: pd.DataFrame) -> pd.DataFrame:
    """Negation of rngskew_63. Higher = calmer, less explosive range
    distribution = quality/fragility premium (M2)."""
    return -_rngskew_63(px)


@factor("rngasym_126")
def _rngasym_126(px: pd.DataFrame) -> pd.DataFrame:
    """Robust asymmetry of the 126-day range distribution, (mean-median)/IQR.
    Higher = a heavy upper tail drags the mean above the median = explosive
    days = jump-risk premium (M1)."""
    rng = _log_range(px)
    w = 126
    mean = rng.rolling(w, min_periods=63).mean()
    q25 = rng.rolling(w, min_periods=63).quantile(0.25)
    q50 = rng.rolling(w, min_periods=63).quantile(0.50)
    q75 = rng.rolling(w, min_periods=63).quantile(0.75)
    return _safe_div(mean - q50, q75 - q25)


@factor("rngexplode_126")
def _rngexplode_126(px: pd.DataFrame) -> pd.DataFrame:
    """Frequency of range explosions: share of the last 126 days whose range
    exceeded twice its trailing 63-day median. Higher = jump-prone name =
    jump-risk premium (M1)."""
    rng = _log_range(px)
    med = rng.rolling(63, min_periods=30).median()
    flag = (rng > 2.0 * med).where(med.notna())
    return flag.rolling(126, min_periods=63).mean()


@factor("rngtailskew_252")
def _rngtailskew_252(px: pd.DataFrame) -> pd.DataFrame:
    """Tail quantile skew of the 252-day range distribution,
    (q95+q05-2*q50)/(q95-q05). Higher = the extreme days are explosive rather
    than sleepy = jump-risk premium (M1)."""
    rng = _log_range(px)
    w = 252
    q05 = rng.rolling(w, min_periods=126).quantile(0.05)
    q50 = rng.rolling(w, min_periods=126).quantile(0.50)
    q95 = rng.rolling(w, min_periods=126).quantile(0.95)
    return _safe_div(q95 + q05 - 2.0 * q50, q95 - q05)
