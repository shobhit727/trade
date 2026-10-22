"""Agent 12 -- wave 1 -- Regime A: TREND CONSISTENCY.

Assignment
----------
"The fraction of up-days in the last 6 months, which measures smoothness
rather than magnitude."

Sign hypothesis (written BEFORE measuring)
------------------------------------------
A name that closed strictly higher on ~70 of the last 126 sessions has a
*persistent* positive drift: the flow that produced it was one-sided and
repeated, not a single gap, not one earnings print. Repeated one-sided flow
is the definition of a trend, and cross-sectional trends in NIFTY-50
constituents are known to persist over 1-6 month horizons. Therefore
HIGHER up-day fraction should rank BETTER.

The negation is registered as its own factor: if the mechanism is real, one of
the two signs must win, and which one wins is itself a finding. (Note the
structural caveat: up-day fraction is a coarse, magnitude-free proxy for the
mean return -- for a roughly symmetric return distribution the up-fraction is
0.5 plus mean/scale -- so it is best read as "shrunk momentum". If momentum
is dead in this universe, up-fraction is likely dead with it. The siblings
below are the ones that can break that dependence on MAGNITUDE, which is the
part of the assignment that is genuinely new information.)

Sibling factors in the same family
----------------------------------
* ``upfrac_252``  -- same statistic over 12 months instead of 6 (horizon
  robustness; the harness already ships a 21-day version, so 126/252 are the
  untested horizons).
* ``avg_run_126`` -- mean LENGTH of the up-day runs, i.e. how *consecutive* the
  winning days are, rather than how frequent they are. A name with 70 up-days
  in 5 runs of 14 is qualitatively different from 70 up-days in 35 runs of 2.
* ``sgn_er_126`` -- signed Kaufman efficiency ratio: net log move divided by
  total path length. This is the canonical "smoothness rather than magnitude"
  measure -- a clean +8% grind (ER 0.85) outranks a +40% chop (ER 0.30).
  Signed, so a smooth FALLER ranks last, which is what a long-only book needs.
* ``er_126``     -- the same ratio unsigned: pure path smoothness regardless of
  direction. Measured, not assumed: it is expected to be a bad long-only signal
  because it promotes smooth decliners.

All factors are pure functions of the CLOSE-price panel, trailing windows
only, and are registered with the shared harness decorator.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.sweep.harness import factor

WIN_6M = 126
WIN_12M = 252
MINP_6M = 63
MINP_12M = 126


# --------------------------------------------------------------------------- #
# Shared primitives
# --------------------------------------------------------------------------- #
def _day_flags(px: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (up_day, usable_day) boolean frames.

    ``up_day`` is True on a bar whose close is strictly above the previous
    bar's close. The first bar of each symbol has no previous close, so it is
    marked *unusable* rather than counted as a down day -- otherwise every
    newly listed name is silently penalised in every up-day statistic.
    """
    valid = px.notna()
    first = valid & ~valid.shift(1, axis=0, fill_value=False)
    usable = valid & ~first
    up = (px.diff() > 0) & usable
    return up, usable


def _up_fraction(px: pd.DataFrame, window: int, minp: int) -> pd.DataFrame:
    """Fraction of *usable* bars in the trailing window that were up days."""
    up, usable = _day_flags(px)
    num = up.astype(float).rolling(window, min_periods=1).sum()
    den = usable.astype(float).rolling(window, min_periods=1).sum()
    frac = num / den.replace(0.0, np.nan)
    return frac.where(den >= minp)


def _avg_run_length(px: pd.DataFrame, window: int, minp: int) -> pd.DataFrame:
    """Mean length of the up-day runs that ENDED inside the trailing window.

    Numerator: number of up bars in the window. Denominator: number of up-run
    STARTS inside the window (an up bar whose predecessor was not up).
    This measures how CONSECUTIVE the winning days are, which is a different
    statistic from how frequent they are.
    """
    up, usable = _day_flags(px)
    prev_up = up.shift(1, axis=0, fill_value=False)
    starts = (up & ~prev_up).astype(float)
    n_up = up.astype(float).rolling(window, min_periods=1).sum()
    n_runs = starts.rolling(window, min_periods=1).sum()
    den = usable.astype(float).rolling(window, min_periods=1).sum()
    out = n_up / n_runs.replace(0.0, np.nan)
    return out.where(den >= minp)


def _efficiency_ratio(px: pd.DataFrame, window: int, minp: int,
                      signed: bool) -> pd.DataFrame:
    """Kaufman efficiency ratio: net log move / total absolute path length.

    Signed=False -> pure smoothness (direction ignored).
    Signed=True  -> smoothness with a direction; a smooth riser scores high,
                     a smooth faller scores low.
    Scale-free in magnitude: this is the part of the assignment that cannot
    be obtained from a return-magnitude factor.
    """
    lpx = np.log(px.where(px > 0))
    lr = lpx.diff()
    net = lr.rolling(window, min_periods=minp).sum()
    path = lr.abs().rolling(window, min_periods=minp).sum()
    num = net if signed else net.abs()
    return num / path.replace(0.0, np.nan)


# --------------------------------------------------------------------------- #
# Factors
# --------------------------------------------------------------------------- #
@factor("upfrac_126")
def _upfrac_126(px: pd.DataFrame) -> pd.DataFrame:
    """ASSIGNMENT: fraction of up-days over the last 126 sessions (6 months).

    Higher = better: repeated one-sided flow is a trend, and trends persist.
    Deliberately magnitude-free -- a name that rose 8% smoothly scores higher
    than one that rose 40% in three gap days.
    """
    return _up_fraction(px, WIN_6M, MINP_6M)


@factor("upfrac_126_neg")
def _upfrac_126_neg(px: pd.DataFrame) -> pd.DataFrame:
    """NEGATION of upfrac_126 -- the mandatory sign test.

    Higher = better means FEWER up days rank higher: the contrarian reading,
    in which a name that has fallen on most days is the one that rebounds.
    If the mechanism is real exactly one of the two signs should win.
    """
    return -_up_fraction(px, WIN_6M, MINP_6M)


@factor("upfrac_252")
def _upfrac_252(px: pd.DataFrame) -> pd.DataFrame:
    """Fraction of up-days over the last 252 sessions (12 months).

    Higher = better: a full year of one-sided flow is a stronger consistency
    statement than half a year, and the harness already ships only the
    21-day version of this statistic.
    """
    return _up_fraction(px, WIN_12M, MINP_12M)


@factor("avg_run_126")
def _avg_run_126(px: pd.DataFrame) -> pd.DataFrame:
    """Mean length of the up-day runs over the last 126 sessions.

    Higher = better: long consecutive winning streaks are direct evidence of
    sustained accumulation, whereas the same number of up days scattered
    across the window is noise. Unlike a max-run statistic this is a ratio, so
    it does not collapse into a handful of tied integers.
    """
    return _avg_run_length(px, WIN_6M, MINP_6M)


@factor("sgn_er_126")
def _sgn_er_126(px: pd.DataFrame) -> pd.DataFrame:
    """Signed efficiency ratio over 126 sessions: net log move / path length.

    Higher = better: a clean, smooth riser outranks a bigger but choppy riser,
    and a smooth faller ranks last. This is the magnitude-free version of
    "trend consistency" and it is the factor in this family that carries
    information the return-magnitude factors cannot see.
    """
    return _efficiency_ratio(px, WIN_6M, MINP_6M, signed=True)


@factor("er_126")
def _er_126(px: pd.DataFrame) -> pd.DataFrame:
    """Unsigned efficiency ratio over 126 sessions: |net log move| / path.

    Higher = better: the purest "smoothness rather than magnitude" measure.
    Direction is deliberately ignored, so for a long-only book this is
    expected to be a POOR signal (it promotes smooth decliners as well as
    smooth risers). Registered to be measured, not assumed.
    """
    return _efficiency_ratio(px, WIN_6M, MINP_6M, signed=False)
