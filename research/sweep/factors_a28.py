"""Agent 28, wave 1 -- rank-change overlays on EXISTING factors.

Assignment (regime B): RANK-BASED MOMENTUM OVERLAY -- apply a rank-change
overlay to an existing factor rather than to price directly.

The neighbouring B assignments already own the plain "change in a name's price
rank over 1/3/6 months" and "acceleration of a name's price rank". This module
therefore ranks an existing FACTOR, not price, and studies the change in that
factor rank:

    signal(t) = rank_cs(factor)(t) - rank_cs(factor)(t - L)

Why a factor-rank change could beat the factor level: the level is a stock of
information accumulated long ago and is dominated by names that have been
strong (or cheap, or quiet) for years. The change isolates the fresh part of
the cross-section -- which names are being re-rated relative to their peers
right now. Both terms are cross-sectional ranks, so market-wide moves cancel:
the signal is a pure relative-re-rating measure, not a beta bet.

H1 (sign +): a name whose factor rank is improving is being repriced, and
underreaction at a 1-month horizon means the improvement persists for 3-6 more
weeks. H0 is the same jump being an overreaction that reverses; every primary
is therefore also registered negated, per the task contract.

Pre-registered: five primaries (four direct, one literal overlay = level plus a
rank-change tilt), lookbacks fixed at 21 and 63 trading days a priori. Nothing
here is selected on the measurement window.
"""

from __future__ import annotations

import pandas as pd

from research.sweep.harness import factor


def _cs_rank(df: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional percentile rank in [0, 1]."""
    return df.rank(axis=1, pct=True)


def _existing(name: str, px: pd.DataFrame) -> pd.DataFrame:
    """Evaluate an already-registered factor.

    The lookup is lazy because agent modules are exec'd from
    ``harness._load_agent_factors()`` while ``harness`` itself is still
    initialising -- importing the registry at module import time is fragile.
    """
    from research.sweep.harness import FACTORS

    fn = FACTORS.get(name)
    if fn is None:
        raise KeyError(f"base factor {name!r} is not registered")
    return fn(px)


def _rankchg(px: pd.DataFrame, base: str, lookback: int) -> pd.DataFrame:
    """Change in the cross-sectional rank of ``base`` over ``lookback`` bars.

    Ranking first and shifting the rank frame keeps both terms point-in-time:
    the rank at t uses only bar t, the rank at t-L uses only bar t-L.
    """
    r = _cs_rank(_existing(base, px))
    return r - r.shift(lookback)


# --- primary factors: direct rank-change form ------------------------------- #
@factor("rankchg_mom")
def _rankchg_mom(px: pd.DataFrame) -> pd.DataFrame:
    """1-month change in the 12-1 momentum rank.

    Isolates names being re-rated on momentum: a name that climbed the momentum
    league table this month is gaining institutional attention. The level of
    mom_12_1 is dominated by moves made up to a year ago; the delta is the
    fresh signal.
    """
    return _rankchg(px, "mom_12_1", 21)


@factor("rankchg_lowvol")
def _rankchg_lowvol(px: pd.DataFrame) -> pd.DataFrame:
    """1-month change in the 63-day low-volatility rank.

    A rising rank means the name is becoming quieter than its peers -- relative
    de-risking. Low-vol is the best-behaved level factor in this panel, so the
    question is whether its *change* adds anything beyond the level.
    """
    return _rankchg(px, "low_vol", 21)


@factor("rankchg_trend")
def _rankchg_trend(px: pd.DataFrame) -> pd.DataFrame:
    """1-month change in the px/MA200 trend rank.

    The level cannot distinguish "crossed above the 200dma last week" from
    "has been above it for a year"; the rank change can. Tests whether the
    fresh crossing, rather than the accumulated trend, is what pays.
    """
    return _rankchg(px, "px_ma200", 21)


@factor("rankchg_mom63")
def _rankchg_mom63(px: pd.DataFrame) -> pd.DataFrame:
    """3-month change in the 12-1 momentum rank. Horizon sensitivity, fixed
    a priori: if the overlay is real it should survive a slower lookback."""
    return _rankchg(px, "mom_12_1", 63)


# --- primary factor: the literal overlay form ------------------------------- #
@factor("overlay_mom")
def _overlay_mom(px: pd.DataFrame) -> pd.DataFrame:
    """Momentum level PLUS a one-month rank-change tilt (weight 0.5, fixed).

    This is the overlay as written in the assignment: the rank change does not
    replace the factor, it tilts selection among names that already score well.
    Equal-ish weight because both terms live on a [0, 1] rank scale.
    """
    level = _cs_rank(_existing("mom_12_1", px))
    delta = _rankchg(px, "mom_12_1", 21)
    return level + 0.5 * delta


# --- sign tests: the reversal hypothesis ------------------------------------ #
# Registered, not assumed. A rank jump is exactly the situation where
# underreaction and overreaction make opposite predictions, so the sign is an
# empirical question and the negations are run on a reduced grid.
@factor("rankchg_mom_neg")
def _rankchg_mom_neg(px: pd.DataFrame) -> pd.DataFrame:
    return -_rankchg(px, "mom_12_1", 21)


@factor("rankchg_lowvol_neg")
def _rankchg_lowvol_neg(px: pd.DataFrame) -> pd.DataFrame:
    return -_rankchg(px, "low_vol", 21)


@factor("rankchg_trend_neg")
def _rankchg_trend_neg(px: pd.DataFrame) -> pd.DataFrame:
    return -_rankchg(px, "px_ma200", 21)


@factor("overlay_mom_neg")
def _overlay_mom_neg(px: pd.DataFrame) -> pd.DataFrame:
    return -_overlay_mom(px)
