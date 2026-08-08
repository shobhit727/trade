'''Flag breakout'''

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class FlagConfig:
    period: int = 5
    quantity: Decimal = Decimal("1")


class FlagStrategy(SignalStrategy):
    name = "flag"

    def __init__(self, config: FlagConfig | None = None):
        super().__init__(config or FlagConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        if len(closes) < self.config.period + 2:
            return 0
        if closes[-1] > closes[-2] and closes[-2] > closes[-3]:
            return 1
        if closes[-1] < closes[-2] and closes[-2] < closes[-3]:
            return -1
        return 0
