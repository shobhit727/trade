"""Streaming OHLCV signal strategy base.

New catalog strategies (`plan.md` §13) subclass :class:`SignalStrategy`, implement
`indicator(...) -> float` (or `signal(...)` for regime fns) and optionally override
`_quant` / bands. The base handles per-symbol rolling buffers, signal->order
conversion (single position per symbol), and is directly runnable by
`backtest.runner` via :meth:`feed`.
"""

from __future__ import annotations

from collections import deque
from decimal import Decimal
from typing import Any

from cryptobot.core.events import OrderEvent, OrderSide, OrderType


class SignalConfig:
    """Base config: extra field names are copied verbatim onto subclasses."""

    quantity: Decimal = Decimal("1")
    position_pct: float = 1.0  # fraction of signal captured per flip
    quick_enter: bool = True
    quick_exit: bool = False


class SignalStrategy:
    """Streaming OHLCV signal strategy with per-symbol rolling buffers.

    `feed(symbol, close, high, low, volume)` maintains windowed arrays and calls
    `signal(closes, highs, lows, volumes)`. Subclasses return +1 (long),
    -1 (short) or 0 (flat). A position flip emits a MARKET OrderEvent.
    """

    name = "signal"

    def __init__(self, config: Any | None = None, maxlen: int = 300):
        self.config = config if config is not None else SignalConfig()
        self._closes: dict[str, deque[float]] = {}
        self._highs: dict[str, deque[float]] = {}
        self._lows: dict[str, deque[float]] = {}
        self._volumes: dict[str, deque[float]] = {}
        self._pos: dict[str, int] = {}
        self._maxlen = maxlen

    # -- subclass hooks ------------------------------------------------------

    def signal(self, closes, highs, lows, volumes) -> float | int:
        """Return -1 (short), 0 (flat) or +1 (long)."""
        return 0

    def warmup(self, closes) -> int:
        """Minimum bars before a signal is actionable (default: config.period)."""
        cfg = self.config
        return getattr(cfg, "period", 20)

    # -- plumbing ------------------------------------------------------------

    def _bufs(self, symbol: str) -> tuple:
        if symbol not in self._closes:
            self._closes[symbol] = deque(maxlen=self._maxlen)
            self._highs[symbol] = deque(maxlen=self._maxlen)
            self._lows[symbol] = deque(maxlen=self._maxlen)
            self._volumes[symbol] = deque(maxlen=self._maxlen)
        return (
            self._closes[symbol],
            self._highs[symbol],
            self._lows[symbol],
            self._volumes[symbol],
        )

    def as_lists(self, symbol: str) -> tuple[list[float], list[float], list[float], list[float]]:
        c, h, lo, v = self._bufs(symbol)
        return list(c), list(h), list(lo), list(v)

    def feed(
        self,
        symbol: str,
        close: float,
        high: float | None = None,
        low: float | None = None,
        volume: float | None = None,
    ) -> OrderEvent | None:
        c, h, lo, v = self._bufs(symbol)
        c.append(float(close))
        h.append(float(high if high is not None else close))
        lo.append(float(low if low is not None else close))
        v.append(float(volume if volume is not None else 0.0))

        closes, highs, lows, volumes = list(c), list(h), list(lo), list(v)
        if len(closes) < self.warmup(closes):
            return None
        sig = self.signal(closes, highs, lows, volumes)
        if sig is None or sig == 0:
            return None
        target = 1 if sig > 0 else -1
        cur = self._pos.get(symbol, 0)
        if target == cur:
            return None
        self._pos[symbol] = target
        return OrderEvent(
            symbol=symbol,
            side=OrderSide.BUY if target > 0 else OrderSide.SELL,
            type=OrderType.MARKET,
            quantity=self.config.quantity,
            strategy=self.name,
        )

    def reset(self, symbol: str | None = None) -> None:
        if symbol is None:
            self._pos.clear()
        elif symbol in self._pos:
            del self._pos[symbol]


def __getattr__(name: str):
    if name == "OrderType":
        from cryptobot.core.events import OrderType

        return OrderType
    raise AttributeError(name)


AnyConfig = Any
