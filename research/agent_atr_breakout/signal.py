"""Vectorised ATR-breakout signal — faithful to the catalog implementation.

Catalog (`src/cryptobot/strategies/catalog/atr_breakout_strategy.py`):

    b = atr(highs, lows, closes, period)        # mean of last `period` true ranges
    m = sma(closes, period)                     # simple moving average
    +1 if close > m + mult*b
    -1 if close < m - mult*b
     0 otherwise

The catalog computes `atr` as the arithmetic mean of the last `period` true ranges
(`indicators.atr`), i.e. an un-smoothed SMA of TR — NOT Wilder's smoothing. That is
reproduced exactly here so this is the same strategy, not a lookalike.

Everything is a trailing window ending at day t inclusive, so the signal on day t
uses no information after t. `run_backtest` then holds weights decided at t from
t+1 onward (one-bar lag), so there is no lookahead anywhere in the chain.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def true_range(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame) -> pd.DataFrame:
    """TR_t = max(H_t - L_t, |H_t - C_{t-1}|, |L_t - C_{t-1}|).

    A bar with no previous close (or a missing one) falls back to H-L, which is the
    only defensible value; those rows are dropped later by the ATR warm-up anyway.
    """
    prev_close = close.shift(1)
    a, b, c = (high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()
    have_prev = prev_close.notna()
    # numpy's maximum propagates NaN (unlike pandas' skipna max), which is what we
    # want: a missing high/low/prev-close must yield a missing TR, not a silently
    # narrower range. The first bar per symbol has no prev_close, so it falls back
    # to H-L and is then discarded by the ATR warm-up window.
    tr = np.fmax(np.fmax(a.to_numpy(), b.to_numpy()), c.to_numpy())
    tr = np.where(have_prev.to_numpy(), tr, a.to_numpy())
    return pd.DataFrame(tr, index=close.index, columns=close.columns)


def atr_panel(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame,
              period: int) -> pd.DataFrame:
    """Un-smoothed (simple) average of the last ``period`` true ranges."""
    return true_range(high, low, close).rolling(period, min_periods=period).mean()


def sma_panel(close: pd.DataFrame, period: int) -> pd.DataFrame:
    return close.rolling(period, min_periods=period).mean()


def signal_panel(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame,
                 period: int, multiplier: float) -> pd.DataFrame:
    """+1 / 0 / -1 exactly as the catalog strategy emits it."""
    b = atr_panel(high, low, close, period)
    m = sma_panel(close, period)
    upper = m + multiplier * b
    lower = m - multiplier * b
    sig = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    valid = b.notna() & m.notna() & close.notna()
    up = valid & (close > upper)
    dn = valid & (close < lower)
    sig[up] = 1.0
    sig[dn] = -1.0
    return sig


def liveness(sig: pd.DataFrame, index: pd.DatetimeIndex) -> float:
    """Fraction of (bar, symbol) cells on which the strategy says long."""
    sub = sig.reindex(index).to_numpy()
    return float(np.nanmean((sub > 0).astype(float)))
