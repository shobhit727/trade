"""Breakout + momentum"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import donchian_high, donchian_low, roc
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class BreakMomentumConfig:
    period: int = 20
    mom_period: int = 10
    quantity: Decimal = Decimal("1")


class BreakMomentumStrategy(SignalStrategy):
    name = "break_momentum"

    def __init__(self, config: BreakMomentumConfig | None = None):
        super().__init__(config or BreakMomentumConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        hh = donchian_high(highs, self.config.period)
        m = roc(closes, self.config.mom_period)
        if hh != hh or m != m:
            return 0
        if closes[-1] >= hh and m > 0:
            return 1
        ll = donchian_low(lows, self.config.period)
        if closes[-1] <= ll and m < 0:
            return -1
        return 0
