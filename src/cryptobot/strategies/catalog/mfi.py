"""Money flow index"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import mfi
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class MfiConfig:
    period: int = 14
    upper: float = 80.0
    lower: float = 20.0
    quantity: Decimal = Decimal("1")


class MfiStrategy(SignalStrategy):
    name = "mfi"

    def __init__(self, config: MfiConfig | None = None):
        super().__init__(config or MfiConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        m = mfi(closes, highs, lows, volumes, self.config.period)
        if m != m:
            return 0
        if m > self.config.upper:
            return -1
        if m < self.config.lower:
            return 1
        return 0
