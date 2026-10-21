"""Wave 1 / agent 15 -- Regime A: CORRELATION TO THE RECENT PAST.

Assignment (research/sweep/families.py, regime A, entry 15):
    "CORRELATION TO THE RECENT PAST: a name's correlation to its own lagged
     returns, distinguishing stable from unstable regimes."

The directive is about a name's OWN return process, not its level, not its
volatility, and not its relation to the market.  The harness already owns
lag-1 autocorrelation (`autocorr`, negated) and a variance ratio
(`variance_ratio`), so nothing here may repeat those two constructions.

Four distinct readings of "correlation to the recent past" are implemented,
each with an explicit sign hypothesis, plus a registered negation of each so
the sign itself is measured rather than assumed:

  acf_persist_63   -- the LEVEL of self-correlation: the mean autocorrelation
                       of daily returns over lags 1..5 in a 63-day window.
  acf_regime_stab  -- the STABILITY of the self-correlation: how dispersed the
                       63-day lag-1 autocorrelation has been over the past year.
  acf_regime_shift -- the DIRECTION of change: recent self-correlation minus
                       the name's own one-year baseline.
  acf_pacf2_63     -- the SHAPE of the memory: partial autocorrelation at
                       lag 2, i.e. self-correlation left after lag 1 is
                       accounted for.

All four are causal: every window is trailing and ends on the current bar.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.sweep.harness import factor

# --------------------------------------------------------------------------- #
# Cached score frames.  The harness re-evaluates a factor on every cell, so
# the expensive rolling algebra is done once per (factor, panel).
# --------------------------------------------------------------------------- #
_CACHE: dict[tuple, pd.DataFrame] = {}


def _cached(key: tuple, builder) -> pd.DataFrame:
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    out = builder()
    _CACHE[key] = out
    return out


def _panel_key(px: pd.DataFrame) -> tuple:
    return (px.shape[0], px.shape[1], str(px.index[0]), str(px.index[-1]))


# --------------------------------------------------------------------------- #
# Rolling autocorrelation of own returns
# --------------------------------------------------------------------------- #
def _acf(r: pd.DataFrame, k: int, w: int, mp: int | None = None) -> pd.DataFrame:
    """Rolling correlation between r_t and r_{t-k} over the trailing ``w`` bars.

    Moment form of Pearson correlation: cov = E[r_s r_{s-k}] - E[r_s]E[r_{s-k}]
    over s in [t-w+1, t], normalised by the two standard deviations.  The
    lagged moments are obtained by shifting the unlagged rolling moments by k,
    so every moment is taken over the same paired sample.  This is ~20x faster
    than ``rolling().corr()`` and numerically identical away from symbol
    inception.

    ``k`` must be >= 1 (a "correlation to the past", never to the future).
    """
    mp = mp if mp is not None else max(10, w // 2)
    prod = (r * r.shift(k)).rolling(w, min_periods=mp).mean()
    m = r.rolling(w, min_periods=mp).mean()
    mk = m.shift(k)
    v = (r * r).rolling(w, min_periods=mp).mean()
    vk = v.shift(k)
    cov = prod - m * mk
    var = np.sqrt((v - m * m).clip(lower=0.0) * (vk - mk * mk).clip(lower=0.0))
    return cov.div(var.replace(0.0, np.nan))


def _acf_mean(r: pd.DataFrame, lags: tuple[int, ...], w: int,
              mp: int | None = None) -> pd.DataFrame:
    """Mean rolling autocorrelation over several lags of the same window."""
    acc = None
    for k in lags:
        a = _acf(r, k, w, mp)
        acc = a if acc is None else acc.add(a, fill_value=np.nan)
    assert acc is not None
    return acc / float(len(lags))


# --------------------------------------------------------------------------- #
# Factors
# --------------------------------------------------------------------------- #
@factor("acf_persist_63")
def _acf_persist_63(px: pd.DataFrame) -> pd.DataFrame:
    """Mean autocorrelation of daily returns over lags 1..5 (63-day window).

    SIGN (primary): HIGHER is better.  A name whose returns are persistently
    self-correlated is in a TRENDING regime -- order flow and herding persist
    rather than cancel -- and a trend at the 1-4 week horizon continues.
    """
    def build() -> pd.DataFrame:
        return _acf_mean(px.pct_change(), (1, 2, 3, 4, 5), 63, mp=32)

    return _cached(("acf_persist_63",) + _panel_key(px), build)


@factor("acf_persist_63_neg")
def _acf_persist_63_neg(px: pd.DataFrame) -> pd.DataFrame:
    """NEGATION of acf_persist_63.

    SIGN (alternative): HIGHER autocorrelation is over-extrapolation, so the
    persistent name is the OVERBOUGHT one and LOW autocorrelation is better.
    The literature supports both readings; which one wins is the finding.
    """
    def build() -> pd.DataFrame:
        return -_acf_mean(px.pct_change(), (1, 2, 3, 4, 5), 63, mp=32)

    return _cached(("acf_persist_63_neg",) + _panel_key(px), build)


@factor("acf_regime_stab")
def _acf_regime_stab(px: pd.DataFrame) -> pd.DataFrame:
    """Negative dispersion of the 63-day lag-1 autocorrelation over 252 days.

    SIGN (primary): HIGHER is better.  A name whose self-correlation has been
    steady is in a STABLE regime: its dynamics can be held through.  A name
    whose autocorrelation swings is UNSTABLE -- regime-churning, fat-tailed,
    and prone to being stopped out inside a 15-30 day holding.
    """
    def build() -> pd.DataFrame:
        fast = _acf(px.pct_change(), 1, 63, mp=32)
        return -fast.rolling(252, min_periods=126).std()

    return _cached(("acf_regime_stab",) + _panel_key(px), build)


@factor("acf_regime_stab_neg")
def _acf_regime_stab_neg(px: pd.DataFrame) -> pd.DataFrame:
    """NEGATION of acf_regime_stab: instability (and its fat tails) is the
    risk premium -- noisy names pay you for tolerating them."""
    def build() -> pd.DataFrame:
        fast = _acf(px.pct_change(), 1, 63, mp=32)
        return fast.rolling(252, min_periods=126).std()

    return _cached(("acf_regime_stab_neg",) + _panel_key(px), build)


@factor("acf_regime_shift")
def _acf_regime_shift(px: pd.DataFrame) -> pd.DataFrame:
    """Recent 63-day lag-1 autocorrelation minus the name's own 252-day
    baseline.  Positive = the name is MOVING INTO a more self-correlated
    (trending) regime; negative = it is moving into a more random one.

    SIGN (primary): HIGHER is better.  A name whose regime is turning
    persistent is where the next leg of the trend lives.
    """
    def build() -> pd.DataFrame:
        r = px.pct_change()
        return _acf(r, 1, 63, mp=32) - _acf(r, 1, 252, mp=126)

    return _cached(("acf_regime_shift",) + _panel_key(px), build)


@factor("acf_regime_shift_neg")
def _acf_regime_shift_neg(px: pd.DataFrame) -> pd.DataFrame:
    """NEGATION of acf_regime_shift: a name whose self-correlation is RISING
    is a crowded, over-extrapolating name and reverts."""
    def build() -> pd.DataFrame:
        r = px.pct_change()
        return _acf(r, 1, 252, mp=126) - _acf(r, 1, 63, mp=32)

    return _cached(("acf_regime_shift_neg",) + _panel_key(px), build)


@factor("acf_pacf2_63")
def _acf_pacf2_63(px: pd.DataFrame) -> pd.DataFrame:
    """Partial autocorrelation at lag 2 of daily returns (63-day window):
    the self-correlation that survives after lag 1 is accounted for.

    SIGN (primary): HIGHER is better.  A positive PACF(2) means extra
    two-day CONTINUATION beyond the lag-1 effect -- an additional memory in
    the direction of the trend, i.e. a name that keeps going its way.
    """
    def build() -> pd.DataFrame:
        r = px.pct_change()
        a1 = _acf(r, 1, 63, mp=32)
        a2 = _acf(r, 2, 63, mp=32)
        den = (1.0 - a1 * a1)
        out = (a2 - a1 * a1) / den.where(den > 1e-6)
        return out.where(a1.abs() < 0.99)

    return _cached(("acf_pacf2_63",) + _panel_key(px), build)


@factor("acf_pacf2_63_neg")
def _acf_pacf2_63_neg(px: pd.DataFrame) -> pd.DataFrame:
    """NEGATION of acf_pacf2_63: extra two-day memory is a squeeze that
    unwinds, so the negative (bounce) reading is better."""
    def build() -> pd.DataFrame:
        r = px.pct_change()
        a1 = _acf(r, 1, 63, mp=32)
        a2 = _acf(r, 2, 63, mp=32)
        den = (1.0 - a1 * a1)
        out = (a2 - a1 * a1) / den.where(den > 1e-6)
        return (-out).where(a1.abs() < 0.99)

    return _cached(("acf_pacf2_63_neg",) + _panel_key(px), build)
