"""Agent 39 -- Regime B: rank churn as an exposure gate, not a stock picker.

The directive is deliberately not "rank by churn". Churn is the *filter*: it
should veto names (or whole rebalance dates) from an otherwise sensible book.

What churn is
-------------
For each date, take every name's cross-sectional percentile rank (the same
information a long-only book consumes), then measure how far that rank travels
over time: mean |rank(t) - rank(t-5)| over the trailing 63 sessions. A name
parked in the top decile has churn near zero; a name oscillating between the
top and bottom quartile has churn near 0.5.

Why it could matter
-------------------
A ranking is only worth trading if it persists. If a name's rank is being
reordered every week, then yesterday's score says little about tomorrow's and
the book pays the full Indian cost stack to chase noise. Churn is therefore a
persistence gate. Direction is genuinely ambiguous -- a persistent winner and a
persistent loser both have low churn, so *level* and *churn* are different
things -- which is why the pure-sign controls are registered in both directions
and measured rather than assumed.

Sign hypotheses (all measured, none assumed)
-------------------------------------------
* ``a39_churn_lo``   : low churn ranks best. Stable relative position = low
  information uncertainty; as a risk premium that should earn *less*, so this
  sign is the "stability is quality" hypothesis, not a given.
* ``a39_churn_hi``   : the negation. Names being constantly re-priced demand a
  premium (or are lottery tickets that underperform). One of the two should win
  if churn carries directional information at all.
* ``a39_churn_gate_mom``    : 12-1 momentum picks, churn vetoes. A momentum name
  whose rank is thrashing is a stale signal, so demote it.
* ``a39_churn_gate_lowvol`` : same gate on the best-documented long-only factor
  in India. If churn is merely a volatility proxy this gate changes nothing;
  if it survives low-vol control it is new information.
* ``a39_churn_veto_comp``   : the literal gate. Hold the production composite,
  but do not rebalance at all on dates when MARKET-WIDE rank churn is in its
  trailing top tercile -- the cross-section is being reordered, so the ranking
  has low persistence and rotating on it buys noise. Churn here decides whether
  the book acts, never which names it holds. Implemented by writing an all-NaN
  score row: the harness treats an unrankable date as "hold what you own".

No lookahead: every input is a trailing statistic of ranks at or before the
current bar. Churn needs close prices only; no OHLC loader is required.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.sweep.harness import FACTORS, factor

_STEP = 5          # rank displacement horizon, sessions
_WIN = 63          # trailing window, sessions (~3 months)
_MIN = _WIN // 2


def _churn(px: pd.DataFrame) -> pd.DataFrame:
    """Mean absolute 5-session displacement of the cross-sectional rank."""
    r = px.rank(axis=1, pct=True)
    return r.diff(_STEP).abs().rolling(_WIN, min_periods=_MIN).mean()


def _xrank(df: pd.DataFrame) -> pd.DataFrame:
    """Per-date percentile rank in [0, 1]; invariant to per-date rescaling."""
    return df.rank(axis=1, pct=True)


def _mom_12_1(px: pd.DataFrame) -> pd.DataFrame:
    return px.pct_change(252) - px.pct_change(231)


def _low_vol(px: pd.DataFrame) -> pd.DataFrame:
    r = px.pct_change()
    return -r.rolling(63, min_periods=30).std() * np.sqrt(252)


@factor("a39_churn_lo")
def _churn_lo(px: pd.DataFrame) -> pd.DataFrame:
    """Low rank churn ranks best -- stable relative position, low uncertainty."""
    return -_churn(px)


@factor("a39_churn_hi")
def _churn_hi(px: pd.DataFrame) -> pd.DataFrame:
    """Opposite sign: names whose rank is being re-priced rank best."""
    return _churn(px)


@factor("a39_churn_gate_mom")
def _churn_gate_mom(px: pd.DataFrame) -> pd.DataFrame:
    """Momentum picks the names, churn vetoes the unstable ones (half weight)."""
    return _xrank(_mom_12_1(px)) - 0.5 * _xrank(_churn(px))


@factor("a39_churn_gate_lowvol")
def _churn_gate_lowvol(px: pd.DataFrame) -> pd.DataFrame:
    """Low-vol picks the names, churn vetoes the unstable ones (half weight)."""
    return _xrank(_low_vol(px)) - 0.5 * _xrank(_churn(px))


@factor("a39_churn_veto_comp")
def _churn_veto_comp(px: pd.DataFrame) -> pd.DataFrame:
    """Production composite, but freeze the book when market-wide churn is high.

    The gate is a trailing tercile so it is a PIT decision; an all-NaN score row
    means the harness finds nothing rankable that date and leaves the portfolio
    untouched, so churn gates *responsiveness*, not name selection.
    """
    base_fn = FACTORS.get("composite_prod")
    base = base_fn(px) if base_fn is not None else _mom_12_1(px)

    mkt_churn = _churn(px).mean(axis=1)
    thr = mkt_churn.rolling(756, min_periods=252).quantile(2.0 / 3.0)
    veto = (mkt_churn > thr).fillna(False).to_numpy(dtype=bool)

    arr = base.to_numpy(dtype=float, copy=True)
    arr[veto, :] = np.nan
    return pd.DataFrame(arr, index=base.index, columns=base.columns)
