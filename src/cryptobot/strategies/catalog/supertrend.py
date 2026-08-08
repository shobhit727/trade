'''Supertrend'''

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import atr
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class SupertrendConfig:
    period: int = 10
    multiplier: float = 3.0
    quantity: Decimal = Decimal("1")


class SupertrendStrategy(SignalStrategy):
    name = "supertrend"

    def __init__(self, config: SupertrendConfig | None = None):
        super().__init__(config or SupertrendConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        b = atr(highs, lows, closes, self.config.period)
        if b != b and len(closes) < self.config.period + 1:
            return 0
        return 1 if closes[-1] > closes[-2] else -1
