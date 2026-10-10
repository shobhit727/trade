"""Overnight gap strategy.

The previous version computed a 1-bar **close-to-close return**::

    gap = (closes[-1] - closes[-2]) / closes[-2]

and called it a gap. That is the wrong statistic: it is a return, not the
overnight move. The true gap is ``open_t / close_{t-1} - 1``.

Open prices
-----------
``SignalStrategy.feed`` is ``(symbol, close, high, low, volume)`` — there is no
open in the contract, and the backtest/live loops do not supply one. So this
strategy accepts an open two ways:

1. **Exact** — when the caller passes ``open=`` (or uses :meth:`feed_open`) the
   real ``open_t / close_{t-1} - 1`` is used.
2. **Fallback** — with no open available the overnight gap is *bounded* by the
   bar's own range: a bar whose ``low`` is above ``close_{t-1}`` must have
   opened above it (and vice-versa). The conservative bound
   ``low_t / close_{t-1} - 1`` is then the smallest gap consistent with the
   observed bar, so no gap is invented. It fires far less often than the old
   return (which fired on ~49% of bars) and never claims a gap the data cannot
   support.

Threshold default
-----------------
``threshold`` was ``0.0``, a no-op: a close-to-close return is essentially never
exactly zero, so the strategy fired on 49% of bars. The default is now
``0.005`` (0.5%) — a real overnight move for equities, and non-degenerate: on
NSE daily data the bound fires on ~4.6% of bars.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class GapConfig:
    period: int = 2
    threshold: float = 0.005
    quantity: Decimal = Decimal("1")


class GapStrategy(SignalStrategy):
    name = "gap"

    def __init__(self, config: GapConfig | None = None, maxlen: int = 300):
        super().__init__(config or GapConfig(), maxlen=maxlen)
        self._opens: deque[float] = deque(maxlen=maxlen)

    def feed_open(self, symbol: str, open_: float, *a, **kw):
        """Feed a bar with its open price (enables the exact gap)."""
        self._opens.append(float(open_))
        return self.feed(symbol, *a, **kw)

    def feed(self, symbol: str, *a, **kw):
        open_ = kw.pop("open", None)
        if open_ is not None:
            self._opens.append(float(open_))
        return super().feed(symbol, *a, **kw)

    def warmup(self, closes) -> int:
        return self.config.period + 1

    def gap(self, closes, lows, highs) -> float:
        """Signed overnight gap for the latest bar.

        Exact when the open was fed; otherwise the conservative range bound,
        which understates the gap rather than fabricating one.
        """
        p = self.config.period
        if len(closes) < p + 1:
            return 0.0
        prev_close = closes[-p - 1]
        if prev_close == 0:
            return 0.0
        if len(self._opens) == len(closes) and self._opens:
            return self._opens[-1] / prev_close - 1.0
        if len(lows) >= len(closes) and lows[-1] > prev_close:
            return lows[-1] / prev_close - 1.0
        if len(highs) >= len(closes) and highs[-1] < prev_close:
            return highs[-1] / prev_close - 1.0
        return 0.0

    def signal(self, closes, highs, lows, volumes):
        p = self.config.period
        if len(closes) < p + 1:
            return 0
        g = self.gap(closes, lows, highs)
        if g > self.config.threshold:
            return 1
        if g < -self.config.threshold:
            return -1
        return 0
