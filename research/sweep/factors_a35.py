"""Agent 35 -- regime B: cross-sectional skew and dispersion.

Two questions. (1) Do extreme names mean-revert more than ordinary names -- i.e.
does the cross-section's *shape* (dispersion, skewness) tell us when extreme
moves are dislocation rather than news? (2) Is there a premium for being in the
tails at all, or does the middle earn more?

Every factor is a pure trailing function of the close panel: no future data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.sweep.harness import factor


def _zc(df: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional z-score that preserves NaN (unlike harness._zcs)."""
    m = df.mean(axis=1)
    s = df.std(axis=1).replace(0, np.nan)
    return df.sub(m, axis=0).div(s, axis=0)


def _centered_rank(df: pd.DataFrame) -> pd.DataFrame:
    return df.rank(axis=1, pct=True) - 0.5


def _trailing_pctile(s: pd.Series, window: int = 252, min_periods: int = 120) -> pd.Series:
    """Percentile of today's value inside its own trailing window (today included)."""
    return s.rolling(window, min_periods=min_periods).rank(pct=True)


def _signed(score: pd.DataFrame, sign: pd.Series) -> pd.DataFrame:
    return score.mul(sign.where(sign.notna()), axis=0)


def _dispersion_switch(px: pd.DataFrame, window: int, high_is_reversal: bool) -> pd.DataFrame:
    disp = px.pct_change(window).std(axis=1)
    pct = _trailing_pctile(disp)
    rev = _centered_rank(-px.pct_change(window))
    sign = pd.Series(np.where(pct >= 0.5, 1.0, -1.0), index=px.index, dtype=float)
    sign = sign.where(pct.notna())
    if not high_is_reversal:
        sign = -sign
    return _signed(rev, sign)


def _skew_switch(px: pd.DataFrame, window: int, fear_is_reversal: bool) -> pd.DataFrame:
    gamma = px.pct_change(window).skew(axis=1)
    state = gamma.rolling(21, min_periods=10).mean()
    sign = pd.Series(np.where(state < 0, -1.0, 1.0), index=px.index, dtype=float)
    sign = sign.where(state.notna())
    if fear_is_reversal:
        sign = -sign
    return _signed(_centered_rank(-px.pct_change(window)), sign)


def _tail_rev(px: pd.DataFrame, window: int = 63, power: float = 4.0) -> pd.DataFrame:
    z = _zc(px.pct_change())
    heavy = z.pow(power).div(1.0 + z.pow(power))
    return -z.mul(heavy).rolling(window, min_periods=window // 2).sum()


@factor("xs_disp_switch21")
def _xs_disp_switch21(px: pd.DataFrame) -> pd.DataFrame:
    """21d reversal when cross-sectional dispersion is high, momentum when low.
    High dispersion marks idiosyncratic dislocation, so the biggest losers bounce."""
    return _dispersion_switch(px, 21, high_is_reversal=True)


@factor("xs_disp_switch21_inv")
def _xs_disp_switch21_inv(px: pd.DataFrame) -> pd.DataFrame:
    """Inverse rule: momentum when dispersion is high, reversal when it is low.
    Tests the opposite reading -- dispersion marks informed repricing that continues."""
    return _dispersion_switch(px, 21, high_is_reversal=False)


@factor("xs_disp_switch5")
def _xs_disp_switch5(px: pd.DataFrame) -> pd.DataFrame:
    """Weekly version: 5d reversal in high-dispersion weeks, 5d momentum in low.
    Short-horizon dislocations should be the most transient and most reverting."""
    return _dispersion_switch(px, 5, high_is_reversal=True)


@factor("xs_disp_switch5_inv")
def _xs_disp_switch5_inv(px: pd.DataFrame) -> pd.DataFrame:
    """Inverse weekly rule: 5d momentum in high dispersion, reversal in low.
    Short-horizon dispersion may instead be news arriving that the market underreacts to."""
    return _dispersion_switch(px, 5, high_is_reversal=False)


@factor("xs_skew_switch21")
def _xs_skew_switch21(px: pd.DataFrame) -> pd.DataFrame:
    """21d reversal when the cross-section is left-skewed, momentum when right-skewed.
    Left skew is panic (a few crashes overshoot); right skew is news (winners keep going)."""
    return _skew_switch(px, 21, fear_is_reversal=True)


@factor("xs_skew_switch21_inv")
def _xs_skew_switch21_inv(px: pd.DataFrame) -> pd.DataFrame:
    """Inverse skew rule: momentum on left skew, reversal on right skew.
    Tests whether crashes continue (fundamental decay) and rallies overshoot."""
    return _skew_switch(px, 21, fear_is_reversal=False)


@factor("xs_avoid_extremes")
def _xs_avoid_extremes(px: pd.DataFrame) -> pd.DataFrame:
    """Negative absolute 63d cross-sectional z: the middle of the pack ranks above the tails.
    Lottery-like extremes are overpriced, so avoiding both tails should beat the universe."""
    return -_zc(px.pct_change(63)).abs()


@factor("xs_seek_extremes")
def _xs_seek_extremes(px: pd.DataFrame) -> pd.DataFrame:
    """Positive absolute 63d cross-sectional z: both tails rank above the middle.
    Tests the opposite claim -- that extreme names carry a positive, not negative, premium."""
    return _zc(px.pct_change(63)).abs()


@factor("xs_tail_rev63")
def _xs_tail_rev63(px: pd.DataFrame) -> pd.DataFrame:
    """63d reversal weighted by daily cross-sectional extremeness (weight ~ z**4).
    Only outsized move days count, so this buys single-event crashes, not slow bleeders."""
    return _tail_rev(px)


@factor("xs_tail_cont63")
def _xs_tail_cont63(px: pd.DataFrame) -> pd.DataFrame:
    """Negation: 63d momentum weighted by daily cross-sectional extremeness.
    Tests whether outsized single-day moves are informed and keep going."""
    return -_tail_rev(px)
