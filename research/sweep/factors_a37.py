"""Agent 37 -- cross-sectional rank acceleration (Regime B).

Hypothesis: what matters for relative performance is not where a name ranks
today but whether it is CLIMBING the cross-section faster than it was.
Formally: rank each name's trailing return against the universe, take the
change in that rank over ``lag`` bars (velocity), then the change in velocity
(acceleration), and subtract the universe's mean acceleration so the factor is
excess acceleration, not a market-wide move.

Mechanism: rank is a scale-free, outlier-proof proxy for relative
institutional demand. A name whose rank improvement is itself speeding up
captures fresh, accelerating flow; a name whose rank climb is decelerating has
already absorbed its flow. The existing catalogue ranks LEVELS (momentum,
trend, reversal); this ranks the second difference of a rank, which is a
different bet.

Sign hypothesis: HIGHER (more positive excess rank acceleration) ranks better.
The negation is registered too -- if the mechanism is real, one of the pair
must win and rank-velocity mean reversion is the competing story.
"""

from __future__ import annotations

import pandas as pd

from research.sweep.harness import factor


def _rank_accel(px: pd.DataFrame, lookback: int, lag: int) -> pd.DataFrame:
    """Excess second difference of cross-sectional percentile rank.

    ``lookback`` is the trailing-return window being ranked; ``lag`` is the
    spacing over which rank velocity and then acceleration are measured. Fully
    causal: every input is at or before the current bar.
    """
    ret = px.pct_change(lookback)
    rank = ret.rank(axis=1, pct=True)
    vel = rank - rank.shift(lag)
    accel = vel - vel.shift(lag)
    return accel.sub(accel.mean(axis=1), axis=0)


@factor("rank_accel_5")
def _rank_accel_5(px: pd.DataFrame) -> pd.DataFrame:
    """Fast: 21d return rank, 5d rank velocity, 5d acceleration."""
    return _rank_accel(px, lookback=21, lag=5)


@factor("rank_accel_21")
def _rank_accel_21(px: pd.DataFrame) -> pd.DataFrame:
    """Mid: 63d return rank, 21d rank velocity, 21d acceleration."""
    return _rank_accel(px, lookback=63, lag=21)


@factor("rank_accel_63")
def _rank_accel_63(px: pd.DataFrame) -> pd.DataFrame:
    """Slow: 126d return rank, 63d rank velocity, 63d acceleration."""
    return _rank_accel(px, lookback=126, lag=63)


@factor("rank_accel_5_neg")
def _rank_accel_5_neg(px: pd.DataFrame) -> pd.DataFrame:
    """Opposite sign of the fast construction: rank climb is decelerating."""
    return -_rank_accel_5(px)


@factor("rank_accel_21_neg")
def _rank_accel_21_neg(px: pd.DataFrame) -> pd.DataFrame:
    """Opposite sign of the mid construction: rank velocity mean-reverts."""
    return -_rank_accel_21(px)
