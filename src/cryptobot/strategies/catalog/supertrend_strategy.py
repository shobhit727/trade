"""Supertrend.

ATR-banded trend system. This module used to compute an ATR and then discard
it: ``signal`` returned ``1 if closes[-1] > closes[-2] else -1``, so ``period``
and ``multiplier`` had no effect on the output (a perturbation sweep over real
NSE daily bars produced byte-identical signals for every multiplier).

Semantics now follow the textbook definition (Kiviat / StockCharts):

* ``atr[i]`` — mean true range over the trailing ``period`` bars (same
  convention as :func:`cryptobot.strategies.indicators.atr`).
* ``hl2[i]`` — mid-point ``(high[i] + low[i]) / 2``.
* basic bands ``hl2 +/- multiplier * atr``.
* the bands ratchet — the upper band only ever falls and the lower only ever
  rises, unless the previous close crossed them (which resets the band).
* the trend flips when the close crosses the active band.

``period`` drives the ATR lookback, ``multiplier`` scales the band width.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import numpy as np

from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class SupertrendConfig:
    period: int = 10
    multiplier: float = 3.0
    quantity: Decimal = Decimal("1")


def _atr_series(highs, lows, closes, period: int) -> list[float]:
    """Rolling mean true range, one entry per bar (NaN before the seed bar)."""
    h = np.asarray(highs, dtype=float)
    lo = np.asarray(lows, dtype=float)
    c = np.asarray(closes, dtype=float)
    prev = np.empty_like(c)
    prev[0] = c[0]
    prev[1:] = c[:-1]
    tr = np.maximum(np.maximum(h - lo, np.abs(h - prev)), np.abs(lo - prev))
    out = np.full(len(c), float("nan"), dtype=float)
    if len(c) >= period + 1:
        out[period:] = np.convolve(tr[1:], np.ones(period) / period, mode="valid")
    return out.tolist()


def _supertrend_trend(highs, lows, closes, period: int, multiplier: float) -> int | None:
    """Direction (+1/-1) of the Supertrend line at the last bar of the window.

    Returns None while the window is too short to seed the ATR. The band
    recursion is inherently sequential, so it is replayed over the supplied
    window on every call; `signal_base` keeps the window bounded by `maxlen`.
    """
    n = len(closes)
    if period < 1 or n < period + 1:
        return None
    mult = float(multiplier)
    atr = _atr_series(highs, lows, closes, period)

    final_up = final_dn = 0.0
    trend = 0
    started = False
    for i in range(period, n):
        a = atr[i]
        if a != a:
            continue
        hl2 = (highs[i] + lows[i]) / 2.0
        up = hl2 + mult * a
        dn = hl2 - mult * a
        if not started:
            final_up, final_dn = up, dn
            trend = 1 if closes[i] > dn else -1
            started = True
            continue
        prev_close = closes[i - 1]
        final_up = up if (up < final_up or prev_close > final_up) else final_up
        final_dn = dn if (dn > final_dn or prev_close < final_dn) else final_dn
        line = final_dn if trend > 0 else final_up
        if closes[i] > line:
            trend = 1
        elif closes[i] < line:
            trend = -1
    return trend if started else None


class SupertrendStrategy(SignalStrategy):
    name = "supertrend"

    def __init__(self, config: SupertrendConfig | None = None):
        super().__init__(config or SupertrendConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        trend = _supertrend_trend(highs, lows, closes, self.config.period, self.config.multiplier)
        if trend is None:
            return 0
        return trend
