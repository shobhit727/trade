"""Regime B -- universe-wide volatility as a CONDITIONING variable.

Identifiability point that shapes every factor here: market volatility is a
single number per date, so on its own it cannot rank the cross-section. It can
only change how a *cross-sectional* signal is weighted. Each regime factor
therefore uses the market-volatility state solely to move weight between two
cross-sectional rankings; none is a timing signal dressed up as a cross-section.

Sign hypotheses are stated in each docstring. Where a mechanism has a natural
opposite, the opposite is registered too, so the data picks the winner.

All inputs are trailing: market return at t is the equal-weight mean of returns
up to and including t, and the regime percentile ranks t's value inside the
trailing 252 observations. The harness trades on the close of t, so this is
point-in-time.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.sweep.harness import _zcs, factor

_ANN = np.sqrt(252.0)


def _mom_12_1(px: pd.DataFrame) -> pd.DataFrame:
    return px.pct_change(252) - px.pct_change(231)


def _low_vol_63(px: pd.DataFrame) -> pd.DataFrame:
    return -px.pct_change().rolling(63, min_periods=30).std() * _ANN


def _market_vol(px: pd.DataFrame, n: int = 21) -> pd.Series:
    """Realised annualised vol of the equal-weight market return."""
    mkt = px.pct_change().mean(axis=1)
    return mkt.rolling(n, min_periods=max(n - 6, 5)).std() * _ANN


def _vol_pct(px: pd.DataFrame) -> pd.Series:
    """Percentile of today's 21d market vol in its trailing 252 observations.

    0 = calmest regime of the past year, 1 = most stressed. Warm-up is the
    neutral 0.5 so early bars (never traded in TEST/TRAIN) stay unbiased.
    """
    mv = _market_vol(px, 21)
    p = mv.rolling(252, min_periods=126).rank(pct=True)
    return p.fillna(0.5)


def _blend(a: pd.DataFrame, b: pd.DataFrame, w: pd.Series) -> pd.DataFrame:
    """(1-w) * z(a) + w * z(b), using the harness's cross-sectional z-score."""
    return _zcs(a).mul(1.0 - w, axis=0) + _zcs(b).mul(w, axis=0)


@factor("a32_mv_mom_rev")
def _mv_mom_rev(px: pd.DataFrame) -> pd.DataFrame:
    """1m reversal in high market-vol regimes, 12-1 momentum in calm ones.

    Higher = better: Nagel (2012) prices short-horizon reversal as compensation
    for liquidity provision, which is worth most when market volatility is high;
    Wang-Xu (2015) find momentum earns more after low-volatility states.
    """
    return _blend(_mom_12_1(px), -px.pct_change(21), _vol_pct(px))


@factor("a32_mv_mom_rev_inv")
def _mv_mom_rev_inv(px: pd.DataFrame) -> pd.DataFrame:
    """The opposite regime tilt: momentum in stress, reversal in calm.

    Registered so the conditioning direction is measured rather than assumed:
    if volatility regimes genuinely matter, exactly one tilt should win.
    """
    return _blend(-px.pct_change(21), _mom_12_1(px), _vol_pct(px))


@factor("a32_mv_mom_def")
def _mv_mom_def(px: pd.DataFrame) -> pd.DataFrame:
    """Low-vol defence in high market-vol regimes, momentum in calm ones.

    Higher = better: flight-to-quality / betting-against-beta is strongest when
    aggregate risk is elevated, while momentum needs a low-vol backdrop.
    """
    return _blend(_mom_12_1(px), _low_vol_63(px), _vol_pct(px))


def _vol_beta(px: pd.DataFrame) -> pd.DataFrame:
    """Trailing 252d beta of each stock's return to changes in market log-vol.

    Uses only data through the current close. Overlapping 21d vol makes the
    regressor autocorrelated, which inflates neither sign nor rank materially.
    """
    r = px.pct_change()
    mkt = r.mean(axis=1)
    mv = mkt.rolling(21, min_periods=15).std()
    d = np.log(mv.replace(0.0, np.nan)).diff()
    cov = r.rolling(252, min_periods=126).cov(d)
    var = d.rolling(252, min_periods=126).var().replace(0.0, np.nan)
    return cov.div(var, axis=0)


@factor("a32_mv_volbeta_low")
def _mv_volbeta_low(px: pd.DataFrame) -> pd.DataFrame:
    """Prefer LOW sensitivity to market-volatility changes.

    Higher = better: Ang-Hodrick-Xing-Zhang (2006) show high vol-beta stocks
    hedge volatility risk and therefore command lower expected returns.
    """
    return -_vol_beta(px)


@factor("a32_mv_volbeta_high")
def _mv_volbeta_high(px: pd.DataFrame) -> pd.DataFrame:
    """Exact negation of a32_mv_volbeta_low -- the sign test for that mechanism."""
    return _vol_beta(px)
