"""Wave-1 agent 36: informational iteration.

Directive (regime B): repeatedly apply a factor to its own output and test
whether compounding the signal amplifies it.

Operationalisation.  For a factor to be composed with itself it must be a map
on panels.  Rank and z-score are idempotent -- rank(rank(x)) == rank(x) -- so
iterating those is a mathematical no-op and tests nothing.  The two operators
below are not idempotent and both compose to something with an economic
reading:

* ``_diff``  D_k(x) = x - x.shift(k).  On log price, D_k is the k-day log
  return; D_k^2 is the change in that return (acceleration); D_k^3 its third
  difference.  A linear operator cannot create information -- D_k^n(log P) is
  a linear combination of the same past prices -- so the prior is that edge
  must NOT compound, only reweight.  The k1/k2/k3 ladder tests exactly that.

* ``_trend`` T_k(x) = x / SMA_k(x).  T is nonlinear (ratio to a trailing
  mean), so T^2 asks whether the trend measure is itself trending.  That is a
  different functional form, not just a reweighting of the same information.

No lookahead: every shift is positive and every rolling window is trailing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.sweep.harness import factor

_K = 21  # rebalance-scale lookback, in trading days


def _diff(x: pd.DataFrame, k: int, order: int) -> pd.DataFrame:
    out = x
    for _ in range(order):
        out = out - out.shift(k)
    return out


def _trend(x: pd.DataFrame, k: int, order: int) -> pd.DataFrame:
    out = x.where(x > 0)
    for _ in range(order):
        ma = out.rolling(k, min_periods=k // 2).mean()
        out = out / ma.replace(0.0, np.nan)
    return out


def _logpx(px: pd.DataFrame) -> pd.DataFrame:
    return np.log(px.where(px > 0))


@factor("iter_mom_k1")
def iter_mom_k1(px: pd.DataFrame) -> pd.DataFrame:
    """21-day log return: un-iterated base of the differencing ladder."""
    return _diff(_logpx(px), _K, 1)


@factor("iter_mom_k2")
def iter_mom_k2(px: pd.DataFrame) -> pd.DataFrame:
    """Change in the 21-day log return: acceleration, the 2nd iteration."""
    return _diff(_logpx(px), _K, 2)


@factor("iter_mom_k3")
def iter_mom_k3(px: pd.DataFrame) -> pd.DataFrame:
    """Third difference of log price: does compounding keep amplifying?"""
    return _diff(_logpx(px), _K, 3)


@factor("iter_mom_k2_neg")
def iter_mom_k2_neg(px: pd.DataFrame) -> pd.DataFrame:
    """Negated acceleration: the overreaction/reversal sign of the same map."""
    return -iter_mom_k2(px)


@factor("iter_trend_k2")
def iter_trend_k2(px: pd.DataFrame) -> pd.DataFrame:
    """Log of the twice-iterated price/SMA50 ratio: is the trend itself trending?"""
    return np.log(_trend(px, 50, 2))
