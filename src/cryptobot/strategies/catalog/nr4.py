'''Nr4 range'''

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import range_n
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class Nr4Config:
    period: int = 4
    quantity: Decimal = Decimal("1")


class Nr4Strategy(SignalStrategy):
    name = "nr4"

    def __init__(self, config: Nr4Config | None = None):
        super().__init__(config or Nr4Config())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        cur = range_n(highs, lows, 1)
        prev = [range_n(highs, lows, i) for i in range(2, self.config.period + 2)]
        if not prev or cur != cur:
            return 0
        if cur <= min(prev):
            return 1 if closes[-1] > closes[-2] else -1
        return 0
