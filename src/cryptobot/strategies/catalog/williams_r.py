'''Williams %r'''

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import williams_r
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class WilliamsRConfig:
    period: int = 14
    lower: float = -80.0
    upper: float = -20.0
    quantity: Decimal = Decimal("1")


class WilliamsRStrategy(SignalStrategy):
    name = "williams_r"

    def __init__(self, config: WilliamsRConfig | None = None):
        super().__init__(config or WilliamsRConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        w = williams_r(closes, highs, lows, self.config.period)
        if w != w:
            return 0
        if w <= self.config.lower:
            return 1
        if w >= self.config.upper:
            return -1
        return 0
