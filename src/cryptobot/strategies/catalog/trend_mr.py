"""Trend + mean reversion"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import sma, zscore
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class TrendMrConfig:
    slow: int = 40
    period: int = 20
    entry: float = 1.5
    quantity: Decimal = Decimal("1")


class TrendMrStrategy(SignalStrategy):
    name = "trend_mr"

    def __init__(self, config: TrendMrConfig | None = None):
        super().__init__(config or TrendMrConfig())

    def warmup(self, closes) -> int:
        return self.config.slow

    def signal(self, closes, highs, lows, volumes):
        t = sma(closes, self.config.slow)
        z = zscore(closes)
        if t != t or z != z:
            return 0
        if z > self.config.entry and closes[-1] > t:
            return 1
        if z < -self.config.entry and closes[-1] < t:
            return -1
        return 0
