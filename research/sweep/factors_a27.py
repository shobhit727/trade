"""Agent 27 -- Regime B, MIDDLE-EXCLUSION.

Directive: hold the top and bottom quartiles but exclude the middle, testing
whether the tails carry the signal.

Construction. The shared harness book is long-only top-N by score, so "hold both
quartiles and drop the middle" has to live in the SCORE: a name scores highest
the further it sits from the cross-sectional median of a base signal.

    tail(sig) = -|rank_pct(sig) - 0.5|

Rank distance, not z distance: the directive is stated in quartiles, and a rank
construction holds an equal NUMBER of names from each tail on every date instead
of letting one fat tail fill the book. The exact negation (+|rank-0.5|) holds
the MIDDLE and is the sign control -- if the middle wins, the base signal is
monotone and tails-only is the wrong implementation.

Close-only: this worktree's harness exposes no OHLC helper, so every factor is a
pure function of the close panel (the same constraint as every built-in factor).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.sweep.harness import FACTORS, factor


def _tail(sig: pd.DataFrame) -> pd.DataFrame:
    """Score maximised at both extremes of ``sig``; the median scores worst."""
    clean = sig.replace([np.inf, -np.inf], np.nan)
    r = clean.rank(axis=1, pct=True)
    return -(r - 0.5).abs()


def _mid(sig: pd.DataFrame) -> pd.DataFrame:
    """Exact negation of :func:`_tail`: the middle scores best."""
    return -_tail(sig)


def _base(name: str, px: pd.DataFrame) -> pd.DataFrame:
    # Resolved at call time: built-ins are registered before agent modules load.
    return FACTORS[name](px)


@factor("a27_mx_mom")
def _mx_mom(px: pd.DataFrame) -> pd.DataFrame:
    """Tails of 12-1 momentum. Hypothesis: momentum's predictive content is
    concentrated in the extreme deciles, so the middle ranks are dilution."""
    return _tail(_base("mom_12_1", px))


@factor("a27_mx_mom_mid")
def _mx_mom_mid(px: pd.DataFrame) -> pd.DataFrame:
    """Control: hold the MIDDLE of 12-1 momentum. Sign test for a27_mx_mom."""
    return _mid(_base("mom_12_1", px))


@factor("a27_mx_skew")
def _mx_skew(px: pd.DataFrame) -> pd.DataFrame:
    """Tails of 126d return skew. Skewness is only priced at the extremes --
    lottery-like right tail versus crash-risk left tail -- so the middle of the
    skew distribution should be the unpriced part."""
    return _tail(_base("skew", px))


@factor("a27_mx_lowvol")
def _mx_lowvol(px: pd.DataFrame) -> pd.DataFrame:
    """Tails of 63d volatility (extremely safe and extremely wild). Tests
    whether the low-vol premium survives being paired with the wild tail."""
    return _tail(_base("low_vol", px))


@factor("a27_mx_comp")
def _mx_comp(px: pd.DataFrame) -> pd.DataFrame:
    """Tails of the rank composite. The practical question: is the production
    composite's alpha carried by its extremes, so the middle can be cut?"""
    return _tail(_base("composite_rank", px))
