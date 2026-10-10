"""Correlation-gated trend strategy.

The trend leg is unchanged (ROC deadband + price vs SMA). What this version
adds is the gate the name promised: the trade is only taken when the symbol's
returns are sufficiently correlated with a market proxy over the rolling window,
i.e. when the move is a market move rather than idiosyncratic noise.

    r_t  = close_t / close_{t-1} - 1                    (symbol returns)
    m_t  = market proxy return at t
    corr = pearson(r[-period:], m[-period:])           (rolling, windowed by period)

    |corr| >= min_correlation -> the gate is open, take the trend leg
    |corr| <  min_correlation -> flat (the trend reading is idiosyncratic)

The previous version contained no correlation statistic at all: it computed
``sma`` and ``roc`` and compared them, so the "gate" was just a ROC deadband.

Market proxy resolution (first match wins) — the single-name ``feed()`` contract
carries no benchmark, so this is explicit rather than implicit:

1. an externally supplied benchmark series (``feed_benchmark`` / ``set_benchmark``)
2. the equal-weight return of every OTHER symbol fed to this same strategy
   instance (a cross-sectional proxy; the base class buffers per symbol)
3. with neither available the proxy is the symbol's own ``period``-bar return.
   **This is not a market** — it measures trend persistence (autocorrelation),
   and the gate is then a persistence filter, not a beta filter. It is documented
   here rather than silently passed off as market correlation.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import roc, sma
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class CorrGateConfig:
    period: int = 20
    threshold: float = 0.01
    min_correlation: float = 0.3
    quantity: Decimal = Decimal("1")


def _returns(closes: list[float]) -> list[float]:
    """1-bar simple returns, one per bar after the first."""
    return [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes)) if closes[i - 1]]


def _pearson(xs: list[float], ys: list[float]) -> float:
    """Pearson correlation of two equal-length series. NaN if undefined."""
    n = len(xs)
    if n < 2 or n != len(ys):
        return float("nan")
    mx = sum(xs) / n
    my = sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0.0 or syy <= 0.0:
        return float("nan")
    return sxy / (sxx * syy) ** 0.5


class CorrGateStrategy(SignalStrategy):
    name = "corr_gate"

    def __init__(self, config: CorrGateConfig | None = None):
        super().__init__(config or CorrGateConfig())
        self._benchmark: deque[float] = deque(maxlen=self.config.period + 2)
        self._cur_symbol = ""

    # -- benchmark plumbing ---------------------------------------------------

    def set_benchmark(self, closes) -> None:
        """Supply an external benchmark close series (index, proxy, ...)."""
        self._benchmark = deque((float(c) for c in closes), maxlen=self.config.period + 2)

    def feed_benchmark(self, close: float) -> None:
        """Append one benchmark close (aligned to the symbol's bar clock)."""
        self._benchmark.append(float(close))

    def feed(self, symbol: str, *a, **kw):
        # signal() has no symbol argument; record which leg is being asked about
        # so the cross-sectional proxy can exclude it.
        self._cur_symbol = symbol
        return super().feed(symbol, *a, **kw)

    def _market_returns(self, closes: list[float]) -> list[float] | None:
        """Proxy returns aligned to ``_returns(closes)``, or None if unavailable."""
        if len(self._benchmark) >= 3:
            return _returns(list(self._benchmark))

        others = [
            list(buf)
            for sym, buf in self._closes.items()
            if sym != self._cur_symbol and len(buf) >= 2
        ]
        if others:
            width = min(len(c) for c in others + [closes])
            legs = [_returns(c[-width:]) for c in others + [closes]]
            bench = [sum(col) / len(col) for col in zip(*legs[:-1], strict=True)]
            own = legs[-1]
            return bench[-len(own) :]

        # No external market available: own period-bar return (persistence proxy).
        p = self.config.period
        if len(closes) < p + 1:
            return None
        drift = [
            closes[i] / closes[i - p] - 1.0 for i in range(p, len(closes)) if closes[i - p]
        ]
        return drift

    def warmup(self, closes) -> int:
        return self.config.period + 2

    def rolling_correlation(self, closes) -> float:
        """Latest rolling correlation of symbol returns against the proxy."""
        period = self.config.period
        if len(closes) < period + 2:
            return float("nan")
        own = _returns(closes)[-period:]
        market = self._market_returns(closes)
        if market is None or len(market) < period:
            return float("nan")
        return _pearson(own, market[-period:])

    def signal(self, closes, highs, lows, volumes):
        period = self.config.period
        if len(closes) < period + 2:
            return 0
        m = sma(closes, period)
        r = roc(closes, period)
        corr = self.rolling_correlation(closes)
        if m != m or r != r or corr != corr:
            return 0
        if abs(corr) < self.config.min_correlation:
            return 0
        if r > self.config.threshold and closes[-1] > m:
            return 1
        if r < -self.config.threshold and closes[-1] < m:
            return -1
        return 0
