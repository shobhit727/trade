"""Volatility expansion"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import range_n
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class VolExpansionConfig:
    period: int = 1
    multiplier: float = 1.8
    quantity: Decimal = Decimal("1")


class VolExpansionStrategy(SignalStrategy):
    name = "vol_expansion"

    def __init__(self, config: VolExpansionConfig | None = None):
        super().__init__(config or VolExpansionConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        cur = range_n(highs, lows, 1)
        base = sum(range_n(highs, lows, i) for i in range(2, 5)) / 3.0
        if cur != cur or base != base or base <= 0:
            return 0
        if closes[-1] > closes[-2] and cur / base > self.config.multiplier:
            return 1
        if closes[-1] < closes[-2] and cur / base > self.config.multiplier:
            return -1
        return 0
