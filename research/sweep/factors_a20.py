"""Agent 20 -- Wave 1. REGIME B: RANK PERSISTENCE.

Hypothesis
----------
How long a name has held its cross-sectional rank is a property of the
*ordering* of the universe, not of any single price series. A name that has
held a high rank for many consecutive days is a name the market has settled
on; a name whose rank is re-drawn every week is one the market cannot agree
about. The assignment asks whether rank stability predicts anything.

Mechanism (the frog-in-the-pan / gradual-information story, Da-Gurun-Warachka):
if information about a firm diffuses *gradually*, its relative ranking moves
in many small steps and the winner keeps winning. If information arrives in
one jump (a price discovery event, a re-rating), the jump is more likely to
reverse. So a persistent, creeping winner should continue, and a jumping
winner should not.

The opposite mechanism is over-extension: a name that has been a leader for a
year is crowded and expensive, and its rank persistence marks it as extended
rather than as information still arriving. Both are tested: every factor here
is registered with its sign hypothesis, and the headline measure is registered
in BOTH signs so the data, not the hypothesis, picks the winner.

Construction
------------
BASE = the cross-sectional percentile rank of the trailing 63-day return
("who is winning right now"), recomputed every day over the names that have a
price that day. All five factors are functions of the rank *path*, not of the
level: they are therefore close to orthogonal to momentum itself (measured
average cross-sectional correlations: |r| <= 0.07 vs mom_12_1 for the three
path factors), which is the point -- if rank persistence works it must work
by something other than being momentum again.

No lookahead: every input at date t uses bars up to and including t.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.sweep.harness import factor

#: Trailing window of the base ranking signal, in trading days.
BASE_LOOKBACK = 63

#: Quintile cut for the "leader" / "loser" buckets.
TOP_Q = 0.8
BOT_Q = 0.2

#: Streak cap. 63 days is one full base-signal turnover cycle; capping stops a
#: single multi-year leader from dominating the top of the book.
STREAK_CAP = 63.0

#: Windows for the path-geometry factors.
AC_WINDOW = 63
PATH_WINDOW = 126

#: Base-rank cache. Keyed by (id(px), lookback); the panel itself is stored
#: alongside so its id cannot be recycled while the cache is live.
_BASE_CACHE: dict[tuple[int, int], tuple[pd.DataFrame, pd.DataFrame]] = {}


def _base_rank(px: pd.DataFrame, lookback: int = BASE_LOOKBACK) -> pd.DataFrame:
    """Cross-sectional percentile rank of the trailing `lookback` return.

    NaN prices (pre-listing) are excluded from that day's cross-section and
    stay NaN, so a name cannot hold a rank it was never eligible for.
    """
    key = (id(px), lookback)
    hit = _BASE_CACHE.get(key)
    if hit is not None:
        return hit[1]
    rank = px.pct_change(lookback).rank(axis=1, pct=True)
    _BASE_CACHE[key] = (px, rank)
    return rank


def _streaks(mask: np.ndarray) -> np.ndarray:
    """Consecutive-True run length ending at each row, per column."""
    t_max, n = mask.shape
    out = np.zeros((t_max, n))
    run = np.zeros(n)
    for t in range(t_max):
        run = np.where(mask[t], run + 1.0, 0.0)
        out[t] = run
    return out


def _signed_streak(rank: pd.DataFrame, cap: float = STREAK_CAP) -> pd.DataFrame:
    """Leader streaks positive, loser streaks negative, capped."""
    top = (rank > TOP_Q).to_numpy()
    bot = (rank < BOT_Q).to_numpy()
    t_max, n = top.shape
    out = np.zeros((t_max, n))
    run_top = np.zeros(n)
    run_bot = np.zeros(n)
    for t in range(t_max):
        run_top = np.where(top[t], run_top + 1.0, 0.0)
        run_bot = np.where(bot[t], run_bot + 1.0, 0.0)
        out[t] = np.minimum(run_top, cap) - np.minimum(run_bot, cap)
    return pd.DataFrame(out, index=rank.index, columns=rank.columns)


def _lag_autocorr(rank: pd.DataFrame, window: int, lag: int = 1) -> pd.DataFrame:
    """Trailing-window autocorrelation of the rank series at `lag` lags.

    Vectorised: rolling sums of r, r^2, r_lag, r_lag^2 and r*r_lag.
    """
    other = rank.shift(lag)
    n = float(window)
    s_r = rank.rolling(window, min_periods=window).sum()
    s_r2 = (rank ** 2).rolling(window, min_periods=window).sum()
    s_o = other.rolling(window, min_periods=window).sum()
    s_o2 = (other ** 2).rolling(window, min_periods=window).sum()
    s_xy = (rank * other).rolling(window, min_periods=window).sum()
    cov = s_xy / n - (s_r / n) * (s_o / n)
    var_r = s_r2 / n - (s_r / n) ** 2
    var_o = s_o2 / n - (s_o / n) ** 2
    return cov / np.sqrt((var_r * var_o).replace(0, np.nan))


@factor("rank_streak_q")
def _rank_streak_q(px: pd.DataFrame) -> pd.DataFrame:
    """Consecutive days a name has held a top (or bottom) quintile rank.

    Sign hypothesis: HIGHER IS BETTER. A name that has held a top-quintile
    rank for many consecutive days is a creeping winner -- information about
    it is still diffusing, so the leadership persists (frog-in-the-pan).
    """
    return _signed_streak(_base_rank(px))


@factor("rank_streak_q_neg")
def _rank_streak_q_neg(px: pd.DataFrame) -> pd.DataFrame:
    """Exact negation of rank_streak_q -- the opposite-sign control.

    Sign hypothesis: HIGHER IS BETTER here means "prefer the persistent
    loser / the name whose leadership is fading". If rank persistence is a
    real effect, one of the two signs must win; which one is the finding.
    """
    return -_signed_streak(_base_rank(px))


@factor("rank_autocorr")
def _rank_autocorr(px: pd.DataFrame) -> pd.DataFrame:
    """Lag-1 autocorrelation of the cross-sectional rank over 63 days.

    Sign hypothesis: HIGHER IS BETTER. A name whose relative position barely
    moves is a name the market has settled on; the ranking is stable, so the
    information behind the ranking is stable and slow-moving rather than
    noise that will be arbitraged away.
    """
    return _lag_autocorr(_base_rank(px), AC_WINDOW, lag=1)


@factor("rank_gradual")
def _rank_gradual(px: pd.DataFrame) -> pd.DataFrame:
    """Gradualness of the rank path: 1 - (largest single-day rank move /
    total absolute rank movement) over 126 days.

    Sign hypothesis: HIGHER IS BETTER. A rank that was earned by many small
    steps is a creeping winner (information still diffusing, momentum
    continues); a rank that was earned by one jump is a price-discovery
    event, and jumping winners are the ones that reverse.
    """
    rank = _base_rank(px)
    move = rank.diff().abs()
    total = move.rolling(PATH_WINDOW, min_periods=60).sum()
    biggest = move.rolling(PATH_WINDOW, min_periods=60).max()
    return 1.0 - (biggest / total.replace(0, np.nan))


@factor("rank_churn")
def _rank_churn(px: pd.DataFrame) -> pd.DataFrame:
    """Negated mean daily rank movement over 126 days: rank stability in
    level rather than in concentration.

    Sign hypothesis: HIGHER IS BETTER. A name the market re-ranks every week
    is one whose relative position is a function of flow rather than of
    fundamentals; the stable name is the one whose position is anchored.
    """
    rank = _base_rank(px)
    move = rank.diff().abs()
    return -move.rolling(PATH_WINDOW, min_periods=60).mean()


@factor("ctl_rev63")
def _ctl_rev63(px: pd.DataFrame) -> pd.DataFrame:
    """CONTROL -- not a candidate factor. Plain 63-day reversal, identical to
    the harness's own ``rev_63``.

    The member of this family that survived the TEST screen
    (``rank_streak_q_neg``) measures *persistent* losers and correlates 0.745
    with 63-day reversal, so the only way to say whether the persistence
    qualifier adds anything is to measure plain reversal on the same cells.
    """
    return -px.pct_change(BASE_LOOKBACK)
