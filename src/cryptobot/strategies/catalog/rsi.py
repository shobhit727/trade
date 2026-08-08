'''Rsi reversion'''

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import rsi
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class RsiConfig:
    period: int = 14
    lower: float = 30.0
    upper: float = 70.0
    quantity: Decimal = Decimal("1")


class RsiStrategy(SignalStrategy):
    name = "rsi"

    def __init__(self, config: RsiConfig | None = None):
        super().__init__(config or RsiConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        r = rsi(closes, self.config.period)
        if r != r:
            return 0
        if r < self.config.lower:
            return 1
        if r > self.config.upper:
            return -1
        return 0
