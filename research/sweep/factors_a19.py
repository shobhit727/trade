"""Agent 19 -- wave 1.

Assignment (Regime A): DOWNSIDE-CAPTURE BEHAVIOUR -- how much of the market's
decline a name captures, as a defensive characteristic.

Mechanism being tested
----------------------
The "downside capture" of a name is the fraction of a market's fall that the
name participates in. Two independent literatures say this should matter:

1. Low-beta / low-volatility anomalies are the strongest equity anomalies in
   India and the rest of EM: names that fall less in market declines earn a
   higher risk-adjusted return (betting-against-beta; the low-vol anomaly).
2. A defensive tilt is what a long-only, cost-bearing book needs most: the
   drawdown avoided is what keeps the equity curve inside the GOAL.md halt
   band, and the book is scored on CAGR after a full statutory cost stack.

So the primary hypothesis is: LESS capture of the market's decline ranks
BETTER, because a defensive name converts a market drawdown into a smaller
book drawdown at the same expected return.

The complementary hypothesis (also tested) is the mirror: capture asymmetry.
A name that takes the full upside of a rally but only a fraction of the
downside is the ideal defensive-aggressive profile, so the SPREAD of up-capture
minus down-capture should also rank better.

All factors here are pure functions of the close-price panel. No lookahead:
every window ends on the current bar. The "market" is the equal-weight
cross-sectional mean of the panel -- deliberately the same construction as the
harness's do-nothing benchmark, so "edge_vs_bench" compares like with like.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.sweep.harness import factor

# --------------------------------------------------------------------------- #
# Shared primitives
# --------------------------------------------------------------------------- #


def _returns(px: pd.DataFrame) -> pd.DataFrame:
    return px.pct_change()


def _market(r: pd.DataFrame) -> pd.Series:
    """Equal-weight cross-sectional mean daily return: the market proxy.

    Same construction as the harness benchmark (hold the whole universe), so a
    capture ratio is measured against the thing the book is actually judged
    against.
    """
    return r.mean(axis=1)


def _row_mask(df: pd.DataFrame, mask: pd.Series) -> pd.DataFrame:
    """Zero the rows of `df` where `mask` is False.

    `axis=0` is mandatory: a bare `df.mul(series)` aligns the Series to the
    DataFrame's COLUMNS, which silently broadcasts a 4629-row mask into a
    47-column frame and turns every factor into an empty book that reads as
    "no edge" rather than "never ran".
    """
    return df.mul(mask.astype(float), axis=0)


def _capture(r: pd.DataFrame, mkt: pd.Series, mask: pd.Series,
             win: int, minp: int) -> pd.DataFrame:
    """Capture of `mkt` by each name on the days selected by `mask`.

        capture_i = sum_t(r_i,t * mask_t) / sum_t(mkt_t * mask_t)

    Both sums carry the same sign (negative on down days, positive on up
    days), so the ratio is positive and ~1.0 for a name that moves with the
    market. Returns NaN when the window contains no selected day.
    """
    m = mask.astype(float)
    den = mkt.mul(m).rolling(win, min_periods=minp).sum()
    num = _row_mask(r, mask).rolling(win, min_periods=minp).sum()
    # axis=0: a bare DataFrame/Series division aligns the Series to the
    # COLUMNS and fabricates a 47 x 4629 frame instead of dividing row-wise.
    return num.div(den, axis=0).replace([np.inf, -np.inf], np.nan)


def _down_capture(r: pd.DataFrame, mkt: pd.Series, win: int,
                  minp: int) -> pd.DataFrame:
    down = mkt < 0
    return _capture(r, mkt, down, win, minp)


def _up_capture(r: pd.DataFrame, mkt: pd.Series, win: int,
                minp: int) -> pd.DataFrame:
    up = mkt > 0
    return _capture(r, mkt, up, win, minp)


def _downside_beta(r: pd.DataFrame, mkt: pd.Series, win: int, minp: int,
                   min_down_days: int) -> pd.DataFrame:
    """OLS slope of r_i on mkt, estimated on market-DOWN days only.

    Computed from rolling masked sums so it stays vectorised:

        Sxy = sum(x*y) - sum(x)sum(y)/n
        Sxx = sum(x^2) - sum(x)^2/n
        beta = Sxy / Sxx,  n = number of down days in the window

    `n` is the count of down days, so the window must contain enough of them
    for the regression to mean anything; below `min_down_days` the estimate is
    NaN rather than a number from five observations.
    """
    d = (mkt < 0).astype(float)
    nd = d.rolling(win, min_periods=minp).sum()
    sx = mkt.mul(d).rolling(win, min_periods=minp).sum()
    sxx = mkt.pow(2).mul(d).rolling(win, min_periods=minp).sum()
    sy = _row_mask(r, mask=(d > 0)).rolling(win, min_periods=minp).sum()
    sxy = _row_mask(r.mul(mkt, axis=0), mask=(d > 0)).rolling(win, min_periods=minp).sum()

    n = nd.replace(0, np.nan)
    sxy_c = sxy.sub(sy.mul(sx, axis=0).div(n, axis=0), axis=0)
    sxx_c = sxx.sub(sx.pow(2).div(n))
    beta = sxy_c.div(sxx_c.replace(0, np.nan), axis=0)
    return beta.where(nd >= min_down_days, axis=0)


def _total_beta(r: pd.DataFrame, mkt: pd.Series, win: int, minp: int) -> pd.DataFrame:
    """Plain CAPM beta of each name against the equal-weight market."""
    mvar = mkt.rolling(win, min_periods=minp).var().replace(0, np.nan)
    beta = pd.DataFrame(index=r.index, columns=r.columns, dtype=float)
    for c in r.columns:
        beta[c] = r[c].rolling(win, min_periods=minp).cov(mkt) / mvar
    return beta


# --------------------------------------------------------------------------- #
# Factors
# --------------------------------------------------------------------------- #


@factor("down_capture_126")
def _down_capture_126(px: pd.DataFrame) -> pd.DataFrame:
    """Downside capture vs the equal-weight market over 126 bars, negated.

    Higher = LESS of the market's decline captured. Mechanism: a defensive
    name loses less when the market falls; low-beta/low-vol names are the
    best-performing decile in India, so lower capture should rank better.
    """
    r = _returns(px)
    mkt = _market(r)
    return -_down_capture(r, mkt, 126, 60)


@factor("up_capture_126")
def _up_capture_126(px: pd.DataFrame) -> pd.DataFrame:
    """Upside capture vs the equal-weight market over 126 bars.

    Higher = MORE of the market's advance captured. Mechanism: participation
    in rallies is the return-generating half of the capture pair; a name that
    only defends and never participates should earn less. Sign is genuinely
    ambiguous, so the negation is registered too.
    """
    r = _returns(px)
    mkt = _market(r)
    return _up_capture(r, mkt, 126, 60)


@factor("capture_spread_126")
def _capture_spread_126(px: pd.DataFrame) -> pd.DataFrame:
    """Up-capture minus down-capture over 126 bars.

    Higher = more upside participation AND less downside participation. This
    is the pure defensive-aggressive asymmetry: take the rally, dodge the
    drawdown. Mechanism: the spread is scale-free, so it does not simply
    re-price beta; it prices the ASYMMETRY of participation.
    """
    r = _returns(px)
    mkt = _market(r)
    return _up_capture(r, mkt, 126, 60) - _down_capture(r, mkt, 126, 60)


@factor("downside_beta_252")
def _downside_beta_252(px: pd.DataFrame) -> pd.DataFrame:
    """Downside (market-down-day) beta over 252 bars, negated.

    Higher = LOWER downside beta, i.e. less market-fall participation.
    Mechanism: the same betting-against-beta logic as down_capture, but
    estimated as a conditional regression rather than a ratio of sums, so it
    is not distorted by the few very large down days.
    """
    r = _returns(px)
    mkt = _market(r)
    return -_downside_beta(r, mkt, 252, 120, 30)


@factor("bear_capture_252")
def _bear_capture_252(px: pd.DataFrame) -> pd.DataFrame:
    """Capture measured only during sustained market DECLINES, negated.

    Higher = less of a bear market's decline captured. Mechanism: single down
    days are noise; the defensive characteristic that matters for a book is
    what happens while the market is actually falling (mkt's own 63-bar return
    negative). A name that holds up through bear regimes, rather than merely
    through random down days, is the one that protects the equity curve.
    """
    r = _returns(px)
    mkt = _market(r)
    bear = mkt.rolling(63, min_periods=30).mean() < 0
    return -_capture(r, mkt, bear, 252, 120)


# --------------------------------------------------------------------------- #
# Negations -- the sign test
# --------------------------------------------------------------------------- #
# If the mechanism above is real, one of the two signs should win. Which one
# wins is itself the finding, so the opposite sign is measured as its own
# factor on the same grid rather than assumed away.


@factor("down_capture_126_neg")
def _down_capture_126_neg(px: pd.DataFrame) -> pd.DataFrame:
    """Negation of down_capture_126: MORE downside capture ranks better."""
    return -_down_capture_126(px)


@factor("up_capture_126_neg")
def _up_capture_126_neg(px: pd.DataFrame) -> pd.DataFrame:
    """Negation of up_capture_126: LESS upside capture ranks better."""
    return -_up_capture_126(px)


@factor("capture_spread_126_neg")
def _capture_spread_126_neg(px: pd.DataFrame) -> pd.DataFrame:
    """Negation of capture_spread_126: less participation asymmetry ranks better."""
    return -_capture_spread_126(px)


# --------------------------------------------------------------------------- #
# Control + decomposition
# --------------------------------------------------------------------------- #
# The sign test above showed that the WINNING direction of this family is
# "MORE capture", not less. That is a claim about beta, so it has to be
# tested against beta itself. These two factors are not new claims; they are
# the falsification test for the family.


@factor("beta_252_control")
def _beta_252_control(px: pd.DataFrame) -> pd.DataFrame:
    """CONTROL, not a claim: plain 252-bar beta vs the equal-weight market.

    If up_capture_126 performs exactly like this, then up_capture is beta
    wearing a new name and the capture family has produced nothing new.
    """
    r = _returns(px)
    mkt = _market(r)
    return _total_beta(r, mkt, 252, 120)


@factor("up_capture_ex_beta_126")
def _up_capture_ex_beta_126(px: pd.DataFrame) -> pd.DataFrame:
    """Up-capture MINUS total beta: the participation that beta does NOT explain.

    Decomposition: r_i = alpha + beta*mkt, so up_capture = beta + (n*alpha) /
    sum(mkt_up). Subtracting beta leaves the market-up-day alpha. If the
    family's edge is pure beta, this residual must die; if it survives, the
    capture construction carries information the plain beta factor does not.
    """
    r = _returns(px)
    mkt = _market(r)
    return _up_capture(r, mkt, 126, 60) - _total_beta(r, mkt, 252, 120)
