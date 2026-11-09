"""Agent 25 / wave 1 -- Regime B: the cross-sectional MAXIMUM.

Every factor here is built from the single best *daily* return in a lookback
window. That statistic is deliberately not a volatility proxy: two names can
have the same 63-day standard deviation while one got there through a single
jackpot session and the other through steady drift. Bali, Cakici & Whitelaw
(2011) find lottery-like names (high MAX) earn low subsequent returns because
lottery seekers overpay for them; the identity of the maximum (who owns the
market's best day) is a separate, sparser signal.

The sign is *not* assumed. India's retail-heavy tape has repeatedly produced
spike continuation rather than lottery avoidance, and the in-sample IC of
``max_day_21`` flips between the 2016-23 and 2024-26 windows. ``spike_mom_21``
is the registered sign-flip control, so the sweep measures the sign instead of
inheriting it from the prior.

Degenerate cross-sections are excluded from the leadership count: on a date
where the panel is ffilled flat, ``max`` is 0.0 for every name and an unguarded
``==`` would crown all 47 names at once. Ties for the maximum (e.g. two
limit-up names) credit every tied name, which is intentional -- the data cannot
distinguish them.
"""

import numpy as np
import pandas as pd

from research.sweep.harness import factor

#: Below this many names with a live return, the cross-section is not a market
#: and a "market-wide best day" is meaningless.
_MIN_NAMES = 20

#: Cap on MAX / sigma. Ten daily sigmas in one session is already an extreme
#: jump; without a cap a near-flat name (vol ~ 0) can produce an infinite ratio
#: that owns the whole cross-section.
_MAX_SIGMA = 10.0


def _daily_max(r: pd.DataFrame, window: int, min_periods: int) -> pd.DataFrame:
    """Largest single-day return over ``window`` sessions (lookahead-free)."""
    return r.rolling(window, min_periods=min_periods).max()


@factor("max_day_5")
def _max_day_5(px: pd.DataFrame) -> pd.DataFrame:
    """Short-horizon lottery: -1 x the largest 1-day return in 5 sessions.

    The MAX premium is documented as strongest at the shortest horizon, where
    the jackpot is still salient to buyers.
    """
    return -_daily_max(px.pct_change(), 5, 4)


@factor("max_day_21")
def _max_day_21(px: pd.DataFrame) -> pd.DataFrame:
    """Canonical MAX(1): -1 x the largest 1-day return in 21 sessions."""
    return -_daily_max(px.pct_change(), 21, 15)


@factor("spike_mom_21")
def _spike_mom_21(px: pd.DataFrame) -> pd.DataFrame:
    """Sign-flip control for ``max_day_21``: +1 x the largest 21-day 1-day return.

    Same statistic, opposite economic story -- a jackpot day is an attention
    event that attracts follow-through buying (spike continuation) rather than
    an overpricing that reverts. Registering both makes the sweep pick the sign
    on out-of-sample data.
    """
    return _daily_max(px.pct_change(), 21, 15)


@factor("max_sigma_21")
def _max_sigma_21(px: pd.DataFrame) -> pd.DataFrame:
    """Vol-neutral MAX: -1 x (largest 21-day 1-day return / 252-day daily vol).

    Raw MAX is ~0.50 rank-correlated with ``low_vol`` and +0.42 with
    ``low_vol_252``, so much of a raw-MAX result would just re-test the low-vol
    factor. Dividing by trailing vol isolates the *jump* from the volatility
    level: the resulting score is ~+0.13 correlated with ``low_vol`` and -0.04
    with ``low_vol_252``, i.e. a genuinely new axis.
    """
    r = px.pct_change()
    vol = r.rolling(252, min_periods=120).std().replace(0.0, np.nan)
    ratio = _daily_max(r, 21, 15).div(vol)
    return -ratio.clip(upper=_MAX_SIGMA)


@factor("lead_cnt_63")
def _lead_cnt_63(px: pd.DataFrame) -> pd.DataFrame:
    """Identity of the maximum: -1 x days in the last 63 this name topped the market.

    Not how *large* the name's best day was but how often it owned the single
    highest return in the universe. Chronic leaders are the names lottery money
    keeps bidding; non-leaders score 0. This is the densest usable form of the
    "who is the maximum" question -- median 1 and p90 3 days per 63, so it is
    sparse but far from binary (unlike a single-day-leader flag).
    """
    r = px.pct_change()
    live = np.isfinite(r)
    n_live = live.sum(axis=1)
    mkt_max = r.max(axis=1)
    usable = (n_live >= _MIN_NAMES) & (mkt_max > 0)

    is_lead = (r.eq(mkt_max, axis=0) & live & (r > 0)).to_numpy(dtype=float)
    is_lead = is_lead * usable.to_numpy(dtype=float)[:, None]
    cnt = pd.DataFrame(is_lead, index=r.index, columns=r.columns)
    return -cnt.rolling(63, min_periods=20).sum()
