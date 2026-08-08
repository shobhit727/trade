'''Rate of change'''

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import roc
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class RocConfig:
    period: int = 10
    threshold: float = 0.01
    quantity: Decimal = Decimal("1")


class RocStrategy(SignalStrategy):
    name = "roc"

    def __init__(self, config: RocConfig | None = None):
        super().__init__(config or RocConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        r = roc(closes, self.config.period)
        if r != r:
            return 0
        if r > self.config.threshold:
            return 1
        if r < -self.config.threshold:
            return -1
        return 0
