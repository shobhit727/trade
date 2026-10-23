"""Wave-1 agent 29 -- advance/decline breadth-differential as a timing signal.

The harness builds a fully-invested equal-weight top-N book from a
cross-sectional RANKING, so a purely date-level timing scalar has no effect:
adding the same number to every name leaves the order unchanged. The
breadth-differential therefore enters in the two ways the book can actually
express it:

  (a) as an INTERACTION with a per-name risk loading -- positive breadth
      rotates the book toward high beta, negative breadth rotates it away;
  (b) as a NaN MASK on the rebalance -- no rebalance happens when the breadth
      regime disagrees with the premise, so the book holds its existing names
      (or stays in cash before the first qualifying rebalance).

Every input is a trailing window ending on the current bar, matching the
harness convention that the score on a rebalance date may use that date's
close.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.sweep.harness import _zcs, factor


def _advance_decline(px: pd.DataFrame, window: int) -> pd.Series:
    """Smoothed (advancers - decliners) / live names, on daily closes."""
    r = px.pct_change()
    live = r.notna()
    adv = ((r > 0) & live).sum(axis=1).astype(float)
    dec = ((r < 0) & live).sum(axis=1).astype(float)
    n = live.sum(axis=1).astype(float)
    adir = (adv - dec) / n.replace(0.0, np.nan)
    return adir.rolling(window, min_periods=max(3, window // 2)).mean()


def _beta(px: pd.DataFrame, window: int = 126) -> pd.DataFrame:
    """Rolling beta to the equal-weight market, using past bars only."""
    r = px.pct_change()
    mkt = r.mean(axis=1)
    mp = max(1, window // 2)
    var = mkt.rolling(window, min_periods=mp).var()
    cov = r.rolling(window, min_periods=mp).cov(mkt)
    return cov.div(var.replace(0.0, np.nan), axis=0)


def _risk_tilt(px: pd.DataFrame) -> pd.DataFrame:
    z_mom = _zcs(px.pct_change(63))
    z_beta = _zcs(_beta(px))
    tilt = np.tanh(2.0 * _advance_decline(px, 10))
    return z_mom.add(z_beta.mul(tilt, axis=0))


def _gated_mom(px: pd.DataFrame, open_when_positive: bool) -> pd.DataFrame:
    z = _zcs(px.pct_change(63))
    adir = _advance_decline(px, 10)
    opens = (adir > 0.0) if open_when_positive else (adir < 0.0)
    shut = ~opens.reindex(z.index).fillna(False).to_numpy(dtype=bool)
    out = z.copy()
    out.loc[shut] = np.nan
    return out


@factor("breadth_risk_tilt")
def _breadth_risk_tilt(px: pd.DataFrame) -> pd.DataFrame:
    """Momentum core tilted toward high beta when the advance-decline spread is
    positive and away from it when negative.
    Higher ranks better because beta earns its premium in broadening
    participation and loses it when participation narrows."""
    return _risk_tilt(px)


@factor("breadth_risk_tilt_neg")
def _breadth_risk_tilt_neg(px: pd.DataFrame) -> pd.DataFrame:
    """Exact negation of breadth_risk_tilt -- the opposite-sign control.
    Higher ranks better if narrow breadth, not broad breadth, is when beta pays."""
    return -_risk_tilt(px)


@factor("breadth_thrust_tilt")
def _breadth_thrust_tilt(px: pd.DataFrame) -> pd.DataFrame:
    """Momentum core tilted by the CHANGE in the advance-decline spread
    (5-day minus 63-day): a breadth thrust rather than its level.
    Higher ranks better because a rapid broadening of participation is an
    earlier risk-on signal than the level itself."""
    z_mom = _zcs(px.pct_change(63))
    z_beta = _zcs(_beta(px))
    thrust = _advance_decline(px, 5) - _advance_decline(px, 63)
    return z_mom.add(z_beta.mul(np.tanh(3.0 * thrust), axis=0))


@factor("breadth_gate_mom")
def _breadth_gate_mom(px: pd.DataFrame) -> pd.DataFrame:
    """63-day momentum refreshed only while the 10-day advance-decline spread is
    positive; otherwise the cross-section is all NaN and no rebalance happens.
    Higher ranks better because momentum needs broad participation; when breadth
    is negative the book is held rather than rotated."""
    return _gated_mom(px, open_when_positive=True)


@factor("breadth_gate_mom_flip")
def _breadth_gate_mom_flip(px: pd.DataFrame) -> pd.DataFrame:
    """Gate-direction control: momentum refreshed only while the advance-decline
    spread is negative.
    Higher ranks better if weak breadth, not strong breadth, is the state in
    which the momentum ranking is worth acting on."""
    return _gated_mom(px, open_when_positive=False)
