'''Gap breakout'''

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class GapConfig:
    period: int = 2
    threshold: float = 0.0
    quantity: Decimal = Decimal("1")


class GapStrategy(SignalStrategy):
    name = "gap"

    def __init__(self, config: GapConfig | None = None):
        super().__init__(config or GapConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        if len(closes) < 2:
            return 0
        gap = (closes[-1] - closes[-2]) / closes[-2]
        if gap > self.config.threshold:
            return 1
        if gap < -self.config.threshold:
            return -1
        return 0
