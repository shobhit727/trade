"""Agent 17 -- Wave 1, Regime A: OPEN-TO-CLOSE DRIFT.

Hypothesis under test
---------------------
The average INTRADAY return, ``close/open - 1``, is a proxy for the quality of
a stock's price discovery. A name that repeatedly closes above its open is
one where buyers are in control for the whole session and the closing auction
keeps resolving higher -- that is what a healthy, informed price-discovery
process looks like. The assignment's hypothesis is therefore "higher intraday
drift ranks better".

The competing hypothesis (which is registered explicitly, because a sign flip
is a finding and not a nuisance): intraday drift is a proxy for LATE-SESSION
SPECULATIVE EXCESS -- liquidity-induced intraday pressure and buying
frenzies that mean-revert -- in which case LOWER intraday drift ranks better.

Both signs are measured. The two are not redundant: the harness's scrambled
null for a negated factor is, by construction, a random N-subset drawn from
the bottom of the ranking, so ``edge_vs_null`` on the negated factor answers
"does picking the WORST intraday-drift names beat a random pick".

Data
----
All bars come from the shared, cleaned production loader
(``research.sweep.harness.ohlc_panel`` / ``ohlc_wide``), so corporate-action
rescaling (loader rule C10) is already applied and no agent-written CSV reader
can disagree with the price panel. No lookahead: every statistic uses only bars
up to and including the current one.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.sweep.harness import factor, ohlc_wide

#: Rolling windows. 21 bars ~ one trading month, 63 ~ one quarter.
SHORT_WINDOW = 21
LONG_WINDOW = 63


def _intraday(px: pd.DataFrame) -> pd.DataFrame:
    """Per-bar intraday return ``close/open - 1``, aligned to the close panel.

    The open panel comes from the same cleaned loader as the close panel, so
    the two are on identical scales. Where a symbol has no bar on a date the
    open is NaN and the intraday return is NaN -- the name is then simply not
    scoreable that day, which is the honest treatment. The open is NOT
    forward-filled: a stale open against a fresh close would fabricate a
    spurious intraday return.
    """
    o = ohlc_wide("open").reindex(index=px.index, columns=px.columns)
    return px.div(o).sub(1.0)


def _drift(px: pd.DataFrame, window: int) -> pd.DataFrame:
    """Mean intraday return over ``window`` bars."""
    return _intraday(px).rolling(window, min_periods=window // 2).mean()


def _tstat(px: pd.DataFrame, window: int) -> pd.DataFrame:
    """Intraday drift per unit of intraday volatility (a t-statistic).

    Separates "steady small upward intraday bias" (high) from "wild swings
    that happened to net positive" (low). This is the quality-of-discovery
    reading of the same idea, with the noise taken out.
    """
    oc = _intraday(px)
    mu = oc.rolling(window, min_periods=window // 2).mean()
    sd = oc.rolling(window, min_periods=window // 2).std()
    return mu.div(sd.replace(0, np.nan))


def _overnight(px: pd.DataFrame) -> pd.DataFrame:
    """Per-bar overnight return ``open/prev_close - 1``.

    The complement of the intraday return: in exact terms the close-to-close
    return of a window is the product of its intraday and overnight returns.
    """
    o = ohlc_wide("open").reindex(index=px.index, columns=px.columns)
    return o.div(px.shift(1)).sub(1.0)


def _excess(px: pd.DataFrame, window: int) -> pd.DataFrame:
    """Intraday drift MINUS overnight drift over ``window`` bars.

    This is the orthogonality-isolating construction: it asks how much of the
    window's return came from the session rather than from the overnight gap.
    Because it is built as a difference of the two legs, it is not a
    re-parameterisation of the close-to-close return that the catalogue
    already contains -- so if the open-to-close decomposition carries any
    unique information, this is where it must show up.
    """
    intraday = _intraday(px).rolling(window, min_periods=window // 2).mean()
    overnight = _overnight(px).rolling(window, min_periods=window // 2).mean()
    return intraday - overnight


def _winrate(px: pd.DataFrame, window: int) -> pd.DataFrame:
    """Fraction of bars that closed above the open.

    The magnitude-free version of drift: a name with one +15% intraday day
    and sixty flat days has high drift but a low win rate, so the two rank
    names differently.
    """
    oc = _intraday(px)
    up = oc.gt(0).astype(float).where(oc.notna())
    return up.rolling(window, min_periods=window // 2).mean()


# --- level factors: the assignment's hypothesis, higher is better ----------- #
@factor("a17_oc_drift_21")
def _a17_oc_drift_21(px: pd.DataFrame) -> pd.DataFrame:
    """Mean intraday return over 21 bars. HIGHER should rank better: persistent
    intraday demand means the closing auction keeps resolving higher, which is
    what good price discovery looks like."""
    return _drift(px, SHORT_WINDOW)


@factor("a17_oc_drift_63")
def _a17_oc_drift_63(px: pd.DataFrame) -> pd.DataFrame:
    """Mean intraday return over 63 bars. HIGHER should rank better: the same
    mechanism with a quarter of history, so less noise and less staleness."""
    return _drift(px, LONG_WINDOW)


@factor("a17_oc_winrate_63")
def _a17_oc_winrate_63(px: pd.DataFrame) -> pd.DataFrame:
    """Share of the last 63 bars that closed above the open. HIGHER should rank
    better: a name that closes up on 80% of its sessions is one where demand
    is structural rather than episodic."""
    return _winrate(px, LONG_WINDOW)


@factor("a17_oc_drift_tstat_63")
def _a17_oc_drift_tstat_63(px: pd.DataFrame) -> pd.DataFrame:
    """63-bar intraday drift per unit of intraday volatility. HIGHER should
    rank better: consistent intraday appreciation, not a lucky high-variance
    stretch."""
    return _tstat(px, LONG_WINDOW)


# --- negated factors: the competing hypothesis, lower should rank better ----- #
@factor("a17_oc_drift_21_neg")
def _a17_oc_drift_21_neg(px: pd.DataFrame) -> pd.DataFrame:
    """NEGATION of a17_oc_drift_21. LOWER intraday drift should rank better if
    intraday strength is late-session speculative excess that mean-reverts."""
    return -_drift(px, SHORT_WINDOW)


@factor("a17_oc_drift_63_neg")
def _a17_oc_drift_63_neg(px: pd.DataFrame) -> pd.DataFrame:
    """NEGATION of a17_oc_drift_63. LOWER should rank better under the
    speculative-excess reading."""
    return -_drift(px, LONG_WINDOW)


@factor("a17_oc_winrate_63_neg")
def _a17_oc_winrate_63_neg(px: pd.DataFrame) -> pd.DataFrame:
    """NEGATION of a17_oc_winrate_63. LOWER should rank better under the
    speculative-excess reading."""
    return -_winrate(px, LONG_WINDOW)


@factor("a17_oc_drift_tstat_63_neg")
def _a17_oc_drift_tstat_63_neg(px: pd.DataFrame) -> pd.DataFrame:
    """NEGATION of a17_oc_drift_tstat_63. LOWER should rank better under the
    speculative-excess reading."""
    return -_tstat(px, LONG_WINDOW)


# --- orthogonality-isolating factor: does the open/close SPLIT carry any
#     information that the close-to-close return does not already carry? ----- #
@factor("a17_oc_excess_63")
def _a17_oc_excess_63(px: pd.DataFrame) -> pd.DataFrame:
    """63-bar intraday drift MINUS 63-bar overnight drift. HIGHER should rank
    better: the return was generated inside the session, where price discovery
    actually happens, rather than at the overnight open."""
    return _excess(px, LONG_WINDOW)


@factor("a17_oc_excess_63_neg")
def _a17_oc_excess_63_neg(px: pd.DataFrame) -> pd.DataFrame:
    """NEGATION of a17_oc_excess_63. LOWER should rank better under the
    speculative-excess reading."""
    return -_excess(px, LONG_WINDOW)
