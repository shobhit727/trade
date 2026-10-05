"""Distance from ma"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import sma
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class DistanceMaConfig:
    period: int = 20
    threshold: float = 0.03
    quantity: Decimal = Decimal("1")


class DistanceMaStrategy(SignalStrategy):
    name = "distance_ma"

    def __init__(self, config: DistanceMaConfig | None = None):
        super().__init__(config or DistanceMaConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        m = sma(closes, self.config.period)
        if m != m or m == 0:
            return 0
        dev = (closes[-1] - m) / m
        if dev > self.config.threshold:
            return -1
        if dev < -self.config.threshold:
            return 1
        return 0
