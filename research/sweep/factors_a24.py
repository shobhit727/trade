"""Agent 24 -- BREADTH OF THE UNIVERSE as a market-timing overlay.

The hypothesis under test: *market-wide* breadth (the fraction of names above
their own moving average) says something about the forward cross-section. Two
distinct mechanisms, both falsifiable:

  1. REGIME (timing). Breadth is a market-wide regime proxy. In a broad advance
     (many names above their MA) risk appetite is high and high-beta /
     high-momentum names should lead; in a narrow or deteriorating tape
     (few names above their MA) the book should rotate to defensives, and
     short-term momentum should reverse rather than continue.
  2. PERSISTENCE (selection). The cross-sectional analogue of breadth is how
     *durably* a single name holds above its own MA. A name that has spent most
     of the last quarter above its 50dma is in a persistent uptrend, which is a
     different bet from being far above the MA *today* (``px_ma50``) or from
     having many up-days (``breadth``).

Methodological note -- read before interpreting the regime factors
------------------------------------------------------------------
The harness builds an ALWAYS-FULLY-INVESTED book of ``n_hold`` names. A
market-wide scalar cannot express "go to cash": if breadth were broadcast to
every symbol, the cross-section would be exactly tied on every date and the book
would degenerate to the hash tie-break basket. Likewise, multiplying a
cross-sectional score by a positive market-wide scalar does not change the
ranking at all. So a breadth *level* cannot be tested here as exposure timing.
What CAN be tested is the consequence breadth has for the RANKING: which names
the book should own in each breadth regime. That is what these factors do. A
clean negative is therefore evidence that breadth does not reorder the
cross-section, NOT that exposure timing is worthless.
"""

from __future__ import annotations

import pandas as pd

from research.sweep.harness import factor

# --- helpers --------------------------------------------------------------- #


def _rank01(df: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional percentile rank in [0, 1]; higher = better."""
    return df.rank(axis=1, pct=True)


def _breadth(px: pd.DataFrame, window: int) -> pd.Series:
    """Fraction of the universe above its own trailing ``window`` MA.

    Trailing only: the MA at date t uses bars up to and including t. NaN names
    (not yet listed) are skipped by ``mean``.
    """
    ma = px.rolling(window, min_periods=max(10, window // 2)).mean()
    return (px > ma).mean(axis=1)


def _mom(px: pd.DataFrame, window: int) -> pd.DataFrame:
    return px.pct_change(window)


def _neg_vol(px: pd.DataFrame, window: int) -> pd.DataFrame:
    """High score = LOW realised volatility (the defensive end)."""
    return -px.pct_change().rolling(window, min_periods=window // 2).std()


def _gate(px: pd.DataFrame, window: int = 50) -> pd.Series:
    """Risk-on indicator: at least half the universe above its own MA."""
    return (_breadth(px, window) >= 0.5).astype(float)


def _switch(px: pd.DataFrame, on: pd.DataFrame, off: pd.DataFrame,
            window: int = 50) -> pd.DataFrame:
    """Pick a cross-sectional ranking per date according to market breadth."""
    g = _gate(px, window)
    a, b = _rank01(on), _rank01(off)
    return a.mul(g, axis=0) + b.mul(1.0 - g, axis=0)


# --- persistence family: per-name time-above-own-MA ------------------------ #
@factor("a24_ma50_frac")
def _ma50_frac(px: pd.DataFrame) -> pd.DataFrame:
    """Fraction of the last 63 bars closing above the name's own 50dma.

    SIGN +: a durable uptrend (price has *held* above its MA, not merely spiked
    through it) is the hallmark of institutional accumulation, and trend
    persistence is the one price-only anomaly documented to survive in Indian
    large caps. Distinct from ``px_ma50`` (distance today) and ``breadth``
    (count of up-days).
    """
    above = (px > px.rolling(50, min_periods=25).mean()).astype(float)
    return above.rolling(63, min_periods=30).mean()


@factor("a24_ma50_frac_neg")
def _ma50_frac_neg(px: pd.DataFrame) -> pd.DataFrame:
    """Exact negation of ``a24_ma50_frac``.

    SIGN -: the opposite bet -- a name that has lived above its 50dma for a
    quarter is crowded/overbought and mean-reverts. Registered because if the
    persistence mechanism is real, exactly one of these two should win on both
    windows; if neither does, the mechanism is absent.
    """
    return -_ma50_frac(px)


# --- regime family: breadth sweeps the cross-sectional book ---------------- #
@factor("a24_brd_switch_mom_def")
def _brd_switch_mom_def(px: pd.DataFrame) -> pd.DataFrame:
    """Breadth regime switch: momentum in a broad tape, defensives in a narrow one.

    SIGN +: breadth50 >= 0.5 -> hold the 63-day winners (risk-on, trend
    continuation). Below 0.5 -> hold the lowest-volatility names (risk-off,
    the only defensive available in a price-only panel). The mechanism is the
    documented momentum crash when market breadth deteriorates: the losing
    names are precisely the crowded high-beta winners, so a fully invested book
    must rotate rather than merely de-risk.
    """
    return _switch(px, _mom(px, 63), _neg_vol(px, 126), window=50)


@factor("a24_brd_switch_mom_inv")
def _brd_switch_mom_inv(px: pd.DataFrame) -> pd.DataFrame:
    """Breadth regime switch on the SIGN of short-term momentum.

    SIGN +: broad tape (breadth50 >= 0.5) -> hold 21-day winners; narrow tape ->
    hold the 21-day LOSERS (rank inverted), i.e. bet on the oversold bounce once
    breadth is washed out. Tests whether breadth is the state variable that
    flips short-horizon momentum from continuation to reversal.
    """
    m = _rank01(_mom(px, 21))
    return _switch(px, m, 1.0 - m, window=50)


@factor("a24_brd_switch_vol_beta")
def _brd_switch_vol_beta(px: pd.DataFrame) -> pd.DataFrame:
    """Breadth regime switch on the volatility (beta proxy) tilt.

    SIGN +: broad tape -> hold the HIGH-volatility names (high beta leads when
    participation is wide); narrow tape -> hold the LOW-volatility names. This is
    a pure beta-timing overlay expressed as a ranking, and it is the sharpest
    test of whether breadth carries regime information at all: it changes the
    book's risk character rather than its momentum exposure.
    """
    v = _rank01(px.pct_change().rolling(126, min_periods=63).std())
    return _switch(px, v, 1.0 - v, window=50)
