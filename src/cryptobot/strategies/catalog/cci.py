'''Cci reversion'''

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import cci
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class CciConfig:
    period: int = 20
    entry: float = 100.0
    quantity: Decimal = Decimal("1")


class CciStrategy(SignalStrategy):
    name = "cci"

    def __init__(self, config: CciConfig | None = None):
        super().__init__(config or CciConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        c = cci(highs, lows, closes, self.config.period)
        if c != c:
            return 0
        if c > self.config.entry:
            return -1
        if c < -self.config.entry:
            return 1
        return 0
