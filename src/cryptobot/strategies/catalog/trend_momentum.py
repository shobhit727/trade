"""Trend + momentum"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import roc, sma
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class TrendMomentumConfig:
    fastperiod: int = 10
    slow: int = 40
    momperiod: int = 15
    threshold: float = 0.01
    quantity: Decimal = Decimal("1")


class TrendMomentumStrategy(SignalStrategy):
    name = "trend_momentum"

    def __init__(self, config: TrendMomentumConfig | None = None):
        super().__init__(config or TrendMomentumConfig())

    def warmup(self, closes) -> int:
        return self.config.slow

    def signal(self, closes, highs, lows, volumes):
        f = sma(closes, self.config.fastperiod)
        s = sma(closes, self.config.slow)
        m = roc(closes, self.config.momperiod)
        if f != f or s != s or m != m:
            return 0
        if f > s and m > self.config.threshold:
            return 1
        if f < s and m < -self.config.threshold:
            return -1
        return 0
