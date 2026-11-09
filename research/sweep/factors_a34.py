"""Agent 34 -- Regime B: tail concentration.

The market-level construct is C_t = (sum of the 3 largest names' absolute move)
/ (sum of all names' absolute move) over a trailing window. That scalar is
*identical across names on a date*, so on its own it cannot rank a
cross-section: every name ties and the book would be decided entirely by the
hash tie-break. These factors are therefore the per-name decompositions of that
same concentration idea -- each answers "how much of the market's move is THIS
name responsible for, and on which side?" -- which is a genuine cross-sectional
question with a testable forward-return implication.

The one place the market-level scalar is usable is as a *portfolio gate*: a book
built from the score but forbidden to re-select on dates when smoothed
concentration sits in the top tercile of its trailing 3-year range. All-NaN score
rows make the harness hold the existing book through that date, which is exactly
"stop buying tail drivers while the market is concentrated". ``a34_conc_gate`` is
that variant of ``a34_tail_share``, so the pair isolates the gate from the score.

Every window is trailing (rolling over bars up to and including t). No shift(-1),
no centred windows, no future access.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.sweep.harness import factor

_WIN_TAIL = 21
_WIN_FREQ = 63
_WIN_ASYM = 63
_WIN_CONC = 21
_PCTL_WIN = 756
_GATE_Q = 0.7
_TOP_K = 3


def _abs_move_share(px: pd.DataFrame, win: int) -> pd.DataFrame:
    """Each name's share of the market's total |return| over ``win`` bars."""
    a = px.pct_change().abs()
    own = a.rolling(win, min_periods=max(3, win // 2)).sum()
    total = own.sum(axis=1).replace(0.0, np.nan)
    return own.div(total, axis=0)


def _top_k_freq(px: pd.DataFrame, win: int = _WIN_FREQ,
                k: int = _TOP_K) -> pd.DataFrame:
    """Fraction of the last ``win`` bars on which the name was one of the k
    largest absolute movers in the cross-section."""
    a = px.pct_change().abs()
    rank = a.rank(axis=1, ascending=False, method="min")
    hit = (rank <= k).astype(float).where(a.notna(), 0.0)
    return hit.rolling(win, min_periods=max(3, win // 2)).mean()


def _up_down_shares(px: pd.DataFrame,
                    win: int = _WIN_ASYM) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split the market's aggregate move into its up and down legs and return
    each name's share of the two legs over ``win`` bars."""
    r = px.pct_change()
    mp = max(3, win // 2)
    up = r.clip(lower=0.0).rolling(win, min_periods=mp).sum()
    dn = (-r.clip(upper=0.0)).rolling(win, min_periods=mp).sum()
    up_share = up.div(up.sum(axis=1).replace(0.0, np.nan), axis=0)
    dn_share = dn.div(dn.sum(axis=1).replace(0.0, np.nan), axis=0)
    return up_share, dn_share


def _market_conc(px: pd.DataFrame) -> pd.Series:
    """C_t: the top-3 names' share of the universe's total absolute move on
    date t. Market-level -- identical across names, so usable only as a gate."""
    a = np.nan_to_num(px.pct_change().abs().to_numpy(dtype=float), nan=0.0)
    total = a.sum(axis=1)
    a.sort(axis=1)
    top = a[:, -_TOP_K:].sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        c = np.divide(top, total, out=np.full_like(top, np.nan), where=total > 0)
    return pd.Series(c, index=px.index)


# --- hypothesis A: tail leadership continues ------------------------------- #
@factor("a34_tail_share")
def _tail_share(px: pd.DataFrame) -> pd.DataFrame:
    """This name's share of the universe's total absolute move over 21 bars.

    Mechanism (+): a name that repeatedly carries a large slice of the market's
    move is where attention, liquidity and flows concentrate; leadership
    persists at weekly/biweekly horizons, so higher share -> higher forward
    return. This is the per-name decomposition of the top-3 concentration
    statistic.
    """
    return _abs_move_share(px, _WIN_TAIL)


# --- hypothesis B: tail leadership is crowding and reverses ---------------- #
@factor("a34_tail_share_neg")
def _tail_share_neg(px: pd.DataFrame) -> pd.DataFrame:
    """Negation of a34_tail_share.

    Mechanism (-): a name that has dominated the market's move is crowded and
    overextended; its tail participation is a lottery/attention premium that
    reverses, so the quiet names outrank the drivers.
    """
    return -_abs_move_share(px, _WIN_TAIL)


@factor("a34_top3_freq_neg")
def _top3_freq_neg(px: pd.DataFrame) -> pd.DataFrame:
    """Negated frequency of being one of the 3 largest absolute movers (63 bars).

    Mechanism (-): repeated top-3 daily moves select the lottery-like,
    high-attention names -- the documented negative-skew/lottery anomaly -- so
    persistent tail movers should underperform. Negated because higher raw
    frequency is hypothesised to be worse.
    """
    return -_top_k_freq(px)


# --- hypothesis C: the *direction* of the tail matters ---------------------- #
@factor("a34_tail_asym")
def _tail_asym(px: pd.DataFrame) -> pd.DataFrame:
    """Up-tail share minus down-tail share of the market's move (63 bars).

    Mechanism (+): two names can carry an equal slice of total movement, but one
    does it on up days and the other on down days. The name whose participation
    is skewed to the upside has convex, resilient exposure; the down-skewed name
    is the market's crash vehicle. Higher asymmetry -> higher forward return.
    """
    up_share, dn_share = _up_down_shares(px)
    return up_share - dn_share


@factor("a34_down_share_neg")
def _down_share_neg(px: pd.DataFrame) -> pd.DataFrame:
    """Negated share of the market's aggregate downside move carried (63 bars).

    Mechanism (-): a name that supplies a large fraction of the market's total
    downside is fragile -- high beta, crowded, crash-sensitive. Negated because
    a large raw downside share is hypothesised to predict lower returns.
    """
    _, dn_share = _up_down_shares(px)
    return -dn_share


# --- hypothesis D: concentration is a market-level RISK gate, not an alpha --- #
@factor("a34_conc_gate")
def _conc_gate(px: pd.DataFrame) -> pd.DataFrame:
    """a34_tail_share, but forced flat (no re-selection) when the top-3 share of
    the market's move is in the top 30% of its trailing 3 years.

    Mechanism: concentration is a risk gauge, not a ranking. When a handful of
    names drive the tape the market is fragile, so fresh entry into the current
    tail leaders is buying exactly the crowded, crash-prone names. Holding the
    prior book through those dates tests the gate against its own ungated twin.
    """
    score = _abs_move_share(px, _WIN_TAIL)
    c = _market_conc(px)
    smooth = c.rolling(_WIN_CONC, min_periods=max(3, _WIN_CONC // 2)).mean()
    thr = smooth.rolling(_PCTL_WIN, min_periods=_PCTL_WIN // 2).quantile(_GATE_Q)
    hot = (smooth > thr).fillna(False)
    return score.mask(hot, np.nan, axis=0)
