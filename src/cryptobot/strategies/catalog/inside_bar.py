"""Inside bar break"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class InsideBarConfig:
    period: int = 2
    quantity: Decimal = Decimal("1")


class InsideBarStrategy(SignalStrategy):
    name = "inside_bar"

    def __init__(self, config: InsideBarConfig | None = None):
        super().__init__(config or InsideBarConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        if len(closes) < 3:
            return 0
        cur = highs[-1] - lows[-1]
        prev = highs[-2] - lows[-2]
        if prev <= 0 or cur > prev * 1.3:
            return 0
        if closes[-1] > highs[-2]:
            return 1
        if closes[-1] < lows[-2]:
            return -1
        return 0
