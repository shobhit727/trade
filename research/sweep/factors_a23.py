"""Wave 1 / agent 23 -- cross-sectional DISPERSION (Regime B).

Directive: does high cross-sectional return dispersion predict mean reversion
across the book?

Mechanism under test
--------------------
When the cross-section is stretched (trailing returns spread far apart), part of
that spread is idiosyncratic noise, not information, so the stretched names give
some of it back. When dispersion is low, moves are more coherent (information
driven) and should persist; the defensible book is then low-vol.

Three constructions, all close-only and free of future bars:
  * regime-conditioned reversal -- blend reversal vs low-vol with a weight that
    rises when cross-sectional dispersion is high vs its own prior-year median;
  * dispersive-day decomposition -- split each name's trailing return into the
    part earned on high-dispersion days and the part earned on coherent days;
  * both sign directions are registered for the two primitive hypotheses.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.sweep.harness import factor

_DISP = 21        # window for "how stretched is the cross-section"
_REG = 252        # baseline window for "is dispersion high?"
_MIN_REG = 120
_DAY = 63         # window for the dispersive-day return decomposition
_MIN_DAY = 30


def _ret(px: pd.DataFrame) -> pd.DataFrame:
    return px.pct_change(fill_method=None)


def _cs_rank(df: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional percentile rank in [0, 1] per date."""
    return df.rank(axis=1, pct=True)


def _dispersion(r: pd.DataFrame, win: int) -> pd.Series:
    """Cross-sectional std of trailing ``win``-day cumulative returns, per date."""
    lc = np.log1p(r).rolling(win, min_periods=max(10, win // 2)).sum()
    return lc.std(axis=1, ddof=1)


def _regime_weight(r: pd.DataFrame) -> pd.Series:
    """Weight in [0, 1], higher when dispersion is high vs its prior-year median.

    ``shift(1)`` keeps today out of its own baseline; today's dispersion is
    measured from returns through today only, so there is no lookahead.
    """
    d = _dispersion(r, _DISP)
    base = d.rolling(_REG, min_periods=_MIN_REG).median().shift(1)
    ratio = d / base.replace(0.0, np.nan)
    w = 0.5 + 0.5 * np.tanh((ratio - 1.0) / 0.30)
    return w.clip(0.0, 1.0).fillna(0.5)


def _disp_day_parts(px: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Risk-scaled trailing returns earned on hot vs coherent days.

    Returns ``(hot_z, tot_z, valid)`` where ``hot_z`` is the part of the 63-day
    return earned on days whose cross-sectional daily dispersion was above its
    shifted prior-year median, ``tot_z`` is the whole 63-day return, both scaled
    by the name's own 63-day realised vol so the raw ranking is not a vol bet.
    """
    r = _ret(px)
    d1 = r.std(axis=1, ddof=1)
    base = d1.rolling(_REG, min_periods=_MIN_REG).median().shift(1)
    hot = (d1 > base) & base.notna()

    cov = r.notna().rolling(_DAY, min_periods=1).sum()
    tot = r.fillna(0.0).rolling(_DAY, min_periods=1).sum()
    hot_ret = r.mul(hot.astype(float), axis=0).fillna(0.0)
    hot_sum = hot_ret.rolling(_DAY, min_periods=1).sum()
    vol = r.rolling(_DAY, min_periods=_MIN_DAY).std() * np.sqrt(_DAY)

    valid = (cov >= _MIN_DAY) & vol.notna() & (vol > 0.0)
    hot_z = (hot_sum / vol).where(valid)
    tot_z = (tot / vol).where(valid)
    return hot_z, tot_z, valid


@factor("a23_disp_cond_rev")
def _disp_cond_rev(px: pd.DataFrame) -> pd.DataFrame:
    """Reversal when dispersion is high, low-vol when it is low.

    Higher ranks the recent loser (high-dispersion regime) or the calmest name
    (low-dispersion regime); the regime weight is a same-date market statistic.
    """
    r = _ret(px)
    rev = _cs_rank(-(px / px.shift(_DISP) - 1.0))
    vol = r.rolling(_DAY, min_periods=_MIN_DAY).std()
    lowvol = _cs_rank(-vol)
    w = _regime_weight(r)
    return rev.mul(w, axis=0) + lowvol.mul(1.0 - w, axis=0)


@factor("a23_disp_cond_rev_neg")
def _disp_cond_rev_neg(px: pd.DataFrame) -> pd.DataFrame:
    """Opposite sign of a23_disp_cond_rev: reversal when dispersion is LOW."""
    return -_disp_cond_rev(px)


@factor("a23_disp_day_rev")
def _disp_day_rev(px: pd.DataFrame) -> pd.DataFrame:
    """Short the risk-scaled return earned on high-dispersion days.

    Higher ranks names whose 63-day move came mostly on dispersive (noisy) days,
    so the book holds names whose dispersive-day run-up has most to give back.
    """
    hot_z, _, _ = _disp_day_parts(px)
    return -hot_z


@factor("a23_disp_day_mom")
def _disp_day_mom(px: pd.DataFrame) -> pd.DataFrame:
    """Opposite sign of a23_disp_day_rev: dispersive-day moves continue."""
    hot_z, _, _ = _disp_day_parts(px)
    return hot_z


@factor("a23_disp_decomp")
def _disp_decomp(px: pd.DataFrame) -> pd.DataFrame:
    """Coherent-day return minus dispersive-day return, risk-scaled.

    Tests the joint mechanism: information earned on coherent days persists while
    the dispersive-day component reverts, so higher should rank better.
    """
    hot_z, tot_z, _ = _disp_day_parts(px)
    return tot_z - 2.0 * hot_z
