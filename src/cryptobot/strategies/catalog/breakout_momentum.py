'''Breakout momentum'''

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import donchian_high, donchian_low
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class BreakoutMomentumConfig:
    period: int = 20
    quantity: Decimal = Decimal("1")


class BreakoutMomentumStrategy(SignalStrategy):
    name = "breakout_momentum"

    def __init__(self, config: BreakoutMomentumConfig | None = None):
        super().__init__(config or BreakoutMomentumConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        hh = donchian_high(highs, self.config.period)
        ll = donchian_low(lows, self.config.period)
        if hh != hh or ll != ll:
            return 0
        if closes[-1] >= hh:
            return 1
        if closes[-1] <= ll:
            return -1
        return 0
