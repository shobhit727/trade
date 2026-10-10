"""ATR trailing stop.

The previous version had no trailing stop at all: no peak, no trail, no stop.
It was an SMA +/- k*ATR band, i.e. a mean-reversion band — the opposite of a
trailing stop.

This is a real Chandelier-style ATR trailing stop, with the running extreme and
the trail kept in per-symbol state:

* entry  — close breaks the prior ``period``-bar extreme
           (long above the prior high, short below the prior low)
* trail  — while in a position the extreme is ratcheted:
           ``stop = peak - multiplier * ATR`` for longs,
           ``stop = trough + multiplier * ATR`` for shorts,
           where peak/trough is the extreme reached *since entry* (never
           retreats).
* exit   — close crosses the stop; the position goes flat and the state resets,
           so the next signal re-enters from scratch.
* flip   — the opposite breakout reverses the position directly.

``config.period`` and ``config.multiplier`` are both live.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import atr
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class AtrTrailingConfig:
    period: int = 14
    multiplier: float = 2.0
    quantity: Decimal = Decimal("1")


class AtrTrailingStrategy(SignalStrategy):
    name = "atr_trailing"

    def __init__(self, config: AtrTrailingConfig | None = None):
        super().__init__(config or AtrTrailingConfig())
        # symbol -> [side, peak, trough]; side is 1 long, -1 short, 0 flat
        self._trail: dict[str, list[float]] = {}
        self._cur_symbol = ""

    def feed(self, symbol: str, *a, **kw):
        # signal() receives no symbol; remember which one is being signalled so
        # the trail state is per-symbol rather than shared.
        self._cur_symbol = symbol
        return super().feed(symbol, *a, **kw)

    def warmup(self, closes) -> int:
        return self.config.period + 1

    def signal(self, closes, highs, lows, volumes):
        p = self.config.period
        if len(closes) < p + 1 or len(highs) < p + 1 or len(lows) < p + 1:
            return 0
        a = atr(highs, lows, closes, p)
        if a != a or a <= 0:
            return 0

        state = self._trail.setdefault(self._cur_symbol, [0.0, 0.0, 0.0])
        side, peak, trough = state
        close = closes[-1]

        # Prior extremes, excluding the current bar.
        prior_high = max(highs[-p - 1 : -1])
        prior_low = min(lows[-p - 1 : -1])

        # 1. breakout / flip entries
        if close > prior_high:
            if side != 1:
                side = 1
            peak = max(close, highs[-1])
            trough = 0.0
        elif close < prior_low:
            if side != -1:
                side = -1
            trough = min(close, lows[-1])
            peak = 0.0
        elif side != 0:
            # 2. ratchet the extreme reached since entry
            if side == 1:
                peak = max(peak, highs[-1])
                stop = peak - self.config.multiplier * a
                if close < stop:
                    side = 0
                    peak = trough = 0.0
            else:
                trough = min(trough, lows[-1])
                stop = trough + self.config.multiplier * a
                if close > stop:
                    side = 0
                    peak = trough = 0.0

        state[0], state[1], state[2] = side, peak, trough
        return int(side)
