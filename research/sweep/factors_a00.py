"""Wave 1 / agent 0 -- ACCELERATION (second differences of momentum).

The directive: *"second differences of momentum. Does the CHANGE in a name's
trend predict better than the level of it?"*

Mechanism under test
--------------------
A name's trend has a level (how far it has moved) and a change (how fast that
level is moving). The change is a *second difference* of price, and it is a
different object from the level:

  * CONTINUATION reading -- an accelerating trend is evidence of fresh,
    directional capital arriving. The marginal buyer is still buying, so the
    change keeps paying for the next few weeks. Higher score = better.
  * EXHAUSTION / REVERSAL reading -- a trend whose momentum is fading is
    about to give the move back; short-horizon momentum in Indian largecaps is
    heavily reversal-dominated, so the *decelerating* name is the one that
    bounces. Higher score = better (negated factor).

These are the SAME factor with opposite signs, so every factor that carries a
sign hypothesis is registered together with its explicit negation and BOTH are
measured. Which one wins is the finding, and a null result on both sides is a
real result: it says the change in a trend carries no information that the
level does not.

One control is included: ``lvl_m63`` is the LEVEL of the same 3-month trend
the acceleration factors are built from, so the "change vs level" question can
be answered on identical cells rather than across agents.

Construction notes
------------------
* All factors are pure functions of the close-price panel, signature
  ``(px: pd.DataFrame) -> pd.DataFrame``, one column per symbol, higher =
  better.
* Acceleration is built from SECOND DIFFERENCES OF LOG PRICE. On a log scale
  the second difference is a genuine curvature (d^2 log P) and is additive
  across sub-periods; the second difference of a simple percentage return is
  not, and it is also scale-dependent in a way that confounds acceleration
  with volatility.
* No lookahead: every construction uses bars up to and including the current
  one. No ``shift(-1)``, no centred windows, no forward fill of scores.
* One factor is volatility-normalised on purpose. A RAW acceleration is
  dominated by the name's own volatility (a ₹1 move in a ₹100 stock and a
  ₹1,000 stock are different percentage points), so an un-normalised
  "acceleration" is largely a high-beta pick. If the raw version shows an
  edge and the normalised one does not, the edge was volatility, not
  acceleration. That is the single most likely way this hypothesis can
  produce a false positive, so the control is measured, not assumed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.sweep.harness import factor


def _logpx(px: pd.DataFrame) -> pd.DataFrame:
    """Natural log of the close panel. Non-positive prices become NaN."""
    return np.log(px.where(px > 0))


# --------------------------------------------------------------------------- #
# Short horizon: acceleration of the 1-month trend
# --------------------------------------------------------------------------- #
@factor("accel_m21")
def _accel_m21(px: pd.DataFrame) -> pd.DataFrame:
    """Second difference of log price at 21-day spacing: is the 1-month trend
    speeding up or slowing down?  Higher = ACCELERATING 1-month trend.
    Continuation reading -- fresh directional capital keeps paying."""
    lp = _logpx(px)
    return lp.diff(21).diff(21)


@factor("accel_m21_n")
def _accel_m21_n(px: pd.DataFrame) -> pd.DataFrame:
    """NEGATION of ``accel_m21``.  Higher = DECELERATING 1-month trend.
    Exhaustion/reversal reading -- a 1-month run that has started to fade
    gives the move back."""
    return -_accel_m21(px)


# --------------------------------------------------------------------------- #
# Medium horizon: acceleration of the 3-month trend (the directive's "trend")
# --------------------------------------------------------------------------- #
@factor("accel_m63")
def _accel_m63(px: pd.DataFrame) -> pd.DataFrame:
    """Second difference of log price at 63-day spacing: the CHANGE in a
    name's quarterly trend.  Higher = ACCELERATING 3-month trend.
    Continuation reading -- a trend that is turning up is being re-rated."""
    lp = _logpx(px)
    return lp.diff(63).diff(63)


@factor("accel_m63_n")
def _accel_m63_n(px: pd.DataFrame) -> pd.DataFrame:
    """NEGATION of ``accel_m63``.  Higher = DECELERATING 3-month trend.
    Exhaustion reading -- a quarterly trend that has rolled over mean-reverts."""
    return -_accel_m63(px)


@factor("accel_trend_d63_d21")
def _accel_trend_d63_d21(px: pd.DataFrame) -> pd.DataFrame:
    """Cross-scale acceleration: the 63-day trend measured now minus the same
    63-day trend measured 21 days ago.  Higher = the quarterly trend is
    IMPROVING NOW but was not a month ago -- an early inflection, not an
    exhausted one.  Unlike ``accel_m63`` the change is measured over a
    shorter window than the trend itself, which is the construction most
    likely to catch a turn before it is obvious."""
    lp = _logpx(px)
    return lp.diff(63).diff(21)


@factor("accel_m63_voladj")
def _accel_m63_voladj(px: pd.DataFrame) -> pd.DataFrame:
    """Volatility-normalised acceleration of the 3-month trend: the second
    difference divided by the name's own 252-day realised volatility.
    Higher = acceleration that is LARGE RELATIVE TO THE NAME'S OWN NOISE.
    This is the control for the obvious confound -- without it, a raw
    acceleration is largely a high-beta pick."""
    lp = _logpx(px)
    r = lp.diff()
    acc = lp.diff(63).diff(63)
    vol = r.rolling(252, min_periods=120).std() * np.sqrt(252)
    return acc / vol.replace(0, np.nan)


@factor("accel_m63_voladj_n")
def _accel_m63_voladj_n(px: pd.DataFrame) -> pd.DataFrame:
    """NEGATION of ``accel_m63_voladj``.  Higher = DECELERATING 3-month trend
    relative to the name's own volatility."""
    return -_accel_m63_voladj(px)


# --------------------------------------------------------------------------- #
# Acceleration of a trend LEVEL (distance to the 200dma) rather than of price
# --------------------------------------------------------------------------- #
@factor("accel_ma_d21_d21")
def _accel_ma_d21_d21(px: pd.DataFrame) -> pd.DataFrame:
    """Second difference of the TREND LEVEL -- the distance above the 200-day
    moving average -- at 21-day spacing.  Higher = the gap to the 200dma is
    widening AND was widening faster last month: a trend accelerating away
    from its own mean."""
    ma = px.rolling(200, min_periods=100).mean()
    dist = px / ma - 1.0
    return dist.diff(21).diff(21)


# --------------------------------------------------------------------------- #
# CONTROL: the LEVEL of the same 3-month trend the accelerations are built
# from.  Not a discovery -- a paired reference so "change vs level" can be
# answered on identical cells.
# --------------------------------------------------------------------------- #
@factor("lvl_m63")
def _lvl_m63(px: pd.DataFrame) -> pd.DataFrame:
    """CONTROL, not a hypothesis: the LEVEL of the 3-month trend (63-day log
    return).  Higher = the name has risen more over 3 months.  Measured on
    the same cells as ``accel_m63`` so the change-vs-level question is
    answered directly."""
    lp = _logpx(px)
    return lp.diff(63)
