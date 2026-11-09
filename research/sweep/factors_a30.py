"""Agent 30 (wave 1) -- Regime B: LEADER-LAG STRUCTURE.

Question: do the top-ranked names lead the rest of the universe, and can a
cross-sectional factor exploit the lead-lag relation?

Construction
------------
At every date t we form a *leader basket* from information available at t:

* momentum leaders   -- top 10 of 47 by trailing 126-day return
* liquidity leaders  -- top 15 of 47 by trailing 63-day rupee volume (the
  institutionally traded names; does not reuse recent return, so it is not
  circular with the signal)

For each stock i we estimate, on a trailing 126-day window, the correlation of
``r_i[t]`` with the *previous* day's leader-basket return. That lag-correlation
is the stock's "follower-ness". Three scores are built from it:

``lead_spill21``      follower-ness x the leader basket's trailing 21-day return
``lead_spill_acc``    trailing 21-day sum of follower-ness x lagged leader return
                      (the realised P&L of actually following the leaders)
``liqlead_spill_acc`` same accumulated score, liquidity-defined leaders

The first is the hypothesis-implied sign (leaders move, followers follow). The
data may reject it, so negations are registered and the direction is measured,
not assumed. A clean negative is a valid result (AGENT_TASK.md).

No lookahead: every input is a trailing window ending at t, the same convention
the harness's own momentum factors use.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from research.sweep.harness import EXCLUDED, _norm, factor

REPO = Path(__file__).resolve().parents[2]

_LOOKBACK = 126          # trailing window for leader rank and lag-correlation
_LEADERS = 10            # momentum-defined leader basket size
_LIQ_LEADERS = 15        # liquidity-defined leader basket size
_LIQ_LOOKBACK = 63       # trailing window for rupee-volume ranking
_FORM = 21               # formation / integration window
_CORR_CLIP = 0.95        # |corr| above this is a degenerate series, not a signal

# Factor functions are called once per cell; the grid re-evaluates the same
# panel 36 times. The tuple keeps a reference to px so the id() key cannot be
# recycled while the entry is alive.
_CACHE: dict[tuple, tuple[pd.DataFrame, pd.DataFrame]] = {}


def _returns(px: pd.DataFrame) -> pd.DataFrame:
    return px.pct_change(fill_method=None)


def _rank_basket(R: pd.DataFrame, lookback: int, k: int) -> pd.Series:
    """Mean return of the top-k names by trailing ``lookback`` return."""
    q = R.rolling(lookback, min_periods=lookback // 2).sum().rank(axis=1, pct=True)
    n = q.notna().sum(axis=1)
    thr = 1.0 - k / n.clip(lower=1)
    out = R.where(q.ge(thr, axis=0)).mean(axis=1)
    return out.replace([np.inf, -np.inf], np.nan)


def _liquidity_basket(px: pd.DataFrame, R: pd.DataFrame) -> pd.Series:
    """Mean return of the top-k names by trailing rupee volume."""
    from research.optimize import splitter as S

    frames: dict[str, pd.Series] = {}
    for f in sorted((REPO / "data" / "nse").glob("*_1d.csv")):
        sym = f.name[: -len("_1d.csv")]
        if sym in EXCLUDED:
            continue
        b = S.bars(sym, timeframe="1d")
        if b.empty or "volume" not in b.columns:
            continue
        frames[_norm(sym).lower()] = b["close"] * b["volume"]
    if not frames:
        return pd.Series(np.nan, index=px.index)
    V = pd.DataFrame(frames).sort_index().reindex(px.index).ffill()
    V = V.reindex(columns=px.columns)
    adv = V.rolling(_LIQ_LOOKBACK, min_periods=_LIQ_LOOKBACK // 2).mean()
    q = adv.rank(axis=1, pct=True)
    n = q.notna().sum(axis=1)
    thr = 1.0 - _LIQ_LEADERS / n.clip(lower=1)
    return R.where(q.ge(thr, axis=0)).mean(axis=1)


def _score(px: pd.DataFrame, *, liq: bool, acc: bool, neg: bool) -> pd.DataFrame:
    ck = (id(px), liq, acc, neg)
    hit = _CACHE.get(ck)
    if hit is not None and hit[0] is px:
        return hit[1]

    R = _returns(px)
    lead = _liquidity_basket(px, R) if liq else _rank_basket(R, _LOOKBACK, _LEADERS)
    lc = R.rolling(_LOOKBACK, min_periods=_LOOKBACK // 2).corr(lead.shift(1))
    lc = lc.where(lc.abs() < _CORR_CLIP)

    form = lead.rolling(_FORM, min_periods=_FORM // 2).sum()
    base = (lc.mul(lead.shift(1), axis=0).rolling(_FORM, min_periods=_FORM // 2).sum()
            if acc else lc.mul(form, axis=0))
    if neg:
        base = base.mul(-1.0)
    base = base.replace([np.inf, -np.inf], np.nan)
    _CACHE[ck] = (px, base)
    return base


@factor("lead_spill21")
def lead_spill21(px: pd.DataFrame) -> pd.DataFrame:
    """Follower-ness x recent leader return. Hypothesis sign: positive."""
    return _score(px, liq=False, acc=False, neg=False)


@factor("lead_spill21_neg")
def lead_spill21_neg(px: pd.DataFrame) -> pd.DataFrame:
    """Negation: if leaders move, followers *reverse* instead of following."""
    return _score(px, liq=False, acc=False, neg=True)


@factor("lead_spill_acc")
def lead_spill_acc(px: pd.DataFrame) -> pd.DataFrame:
    """Trailing realised P&L of following the leaders over the formation month."""
    return _score(px, liq=False, acc=True, neg=False)


@factor("lead_spill_acc_neg")
def lead_spill_acc_neg(px: pd.DataFrame) -> pd.DataFrame:
    """Negation of the accumulated spillover score."""
    return _score(px, liq=False, acc=True, neg=True)


@factor("liqlead_spill_acc")
def liqlead_spill_acc(px: pd.DataFrame) -> pd.DataFrame:
    """Accumulated spillover where leaders are the most-traded names, not winners."""
    return _score(px, liq=True, acc=True, neg=False)
