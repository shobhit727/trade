"""Cointegration pairs strategy.

The previous version had no pair, no spread and no hedge ratio: it was a
single-name z-score mean reversion applied to a trending price — the statistic
least likely to mean-revert. It is now a real pairs strategy:

    hedge ratio  beta = cov(log A, log B) / var(log B)      (OLS, windowed by period)
    spread       s_t  = log A_t - beta * log B_t
    z            z_t  = (s_t - mean(s[-period:])) / std(s[-period:])
    signal       +1 (long A / short B) when z <= -entry, -1 on the mirror, else flat

Pair selection
--------------
``SignalStrategy.signal(closes, highs, lows, volumes)`` is single-name, so the
second leg has to come from the base class's per-symbol buffers. It is resolved
in this order:

1. ``config.symbol_b``, or whatever ``set_leg_b`` pinned.
2. the most recently updated other symbol already buffered by this instance.

**Known limitation:** the shipped backtest/live loops
(``backtest.runner.run_backtest``, ``live.multi_trader``) feed exactly one symbol
per strategy instance, so in those paths no partner is ever buffered and the
strategy is correctly flat. A pairs strategy cannot trade without a pair; it is
flat rather than silently trading a single-name proxy. ``tests/strategies/
test_catalog_cointegration.py`` feeds only ``"BTC"``, so that test also sees no
signals — feed two symbols to exercise this strategy.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class CointegrationConfig:
    period: int = 30
    entry: float = 1.0
    symbol_b: str | None = None
    quantity: Decimal = Decimal("1")


def _hedge_ratio(log_a: list[float], log_b: list[float]) -> float:
    """OLS slope of log_a on log_b (the Engle-Granger hedge ratio)."""
    n = len(log_a)
    if n < 2 or n != len(log_b):
        return float("nan")
    mean_a = sum(log_a) / n
    mean_b = sum(log_b) / n
    cov = sum((a - mean_a) * (b - mean_b) for a, b in zip(log_a, log_b, strict=True))
    var_b = sum((b - mean_b) ** 2 for b in log_b)
    if var_b <= 0.0:
        return float("nan")
    return cov / var_b


def cointegration_zscore(
    closes_a: list[float], closes_b: list[float], period: int
) -> float:
    """Rolling z-score of the log-price spread ``log A - beta*log B``.

    The hedge ratio is re-estimated over the same trailing window as the spread,
    using bars up to and including the current one (no lookahead).
    """
    import math

    n = min(len(closes_a), len(closes_b))
    if n < period + 1:
        return float("nan")
    a = closes_a[-n:]
    b = closes_b[-n:]
    if any(x <= 0 or y <= 0 for x, y in zip(a, b, strict=True)):
        return float("nan")
    log_a = [math.log(x) for x in a]
    log_b = [math.log(y) for y in b]

    window_a = log_a[-period:]
    window_b = log_b[-period:]
    beta = _hedge_ratio(window_a, window_b)
    if beta != beta:
        return float("nan")

    spread = [la - beta * lb for la, lb in zip(log_a, log_b, strict=True)]
    recent = spread[-period:]
    mean = sum(recent) / period
    var = sum((s - mean) ** 2 for s in recent) / period
    sd = var**0.5
    if sd == 0:
        return 0.0
    return (spread[-1] - mean) / sd


class CointegrationStrategy(SignalStrategy):
    """Trades the stationary spread of a cointegrating pair."""

    name = "cointegration"

    def __init__(self, config: CointegrationConfig | None = None):
        super().__init__(config or CointegrationConfig())
        self._leg_b: str | None = self.config.symbol_b
        self._seen: list[str] = []
        self._cur_symbol = ""

    def set_leg_b(self, symbol: str) -> None:
        """Pin the second leg explicitly."""
        self._leg_b = symbol

    def feed(self, symbol: str, *a, **kw):
        self._cur_symbol = symbol
        if symbol not in self._seen:
            self._seen.append(symbol)
        return super().feed(symbol, *a, **kw)

    def _partner(self) -> list[float] | None:
        """Closes of the second leg, or None when no pair is available."""
        candidates = []
        if self._leg_b is not None and self._leg_b != self._cur_symbol:
            # Pinned partner, unless we are being asked about that very symbol
            # (fall through to another buffered symbol in that case).
            candidates.append(self._leg_b)
        candidates.extend(s for s in reversed(self._seen) if s != self._cur_symbol)
        for sym in candidates:
            buf = self._closes.get(sym)
            if buf is not None and len(buf) >= self.config.period + 1:
                return list(buf)
        return None

    def warmup(self, closes) -> int:
        return self.config.period + 1

    def signal(self, closes, highs, lows, volumes):
        if len(closes) < self.config.period + 1:
            return 0
        partner = self._partner()
        if partner is None:
            return 0
        # The two legs are not fed at the same point in the bar clock, so their
        # buffers can differ in length by a bar. Truncate the longer series from
        # the RIGHT so both end on the same timestamp — otherwise bar t of one leg
        # is paired with bar t-1 of the other.
        n = min(len(closes), len(partner))
        a = list(closes[len(closes) - n :])
        b = partner[len(partner) - n :]
        z = cointegration_zscore(a, b, self.config.period)
        if z != z:
            return 0
        if z <= -self.config.entry:
            return 1  # spread cheap -> long A, short B
        if z >= self.config.entry:
            return -1  # spread rich -> short A, long B
        return 0
