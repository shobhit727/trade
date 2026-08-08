"""Momentum + volatility"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import atr, roc
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class MomentumVolConfig:
    period: int = 14
    momperiod: int = 20
    threshold: float = 0.01
    quantity: Decimal = Decimal("1")


class MomentumVolStrategy(SignalStrategy):
    name = "momentum_vol"

    def __init__(self, config: MomentumVolConfig | None = None):
        super().__init__(config or MomentumVolConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        m = roc(closes, self.config.momperiod)
        b = atr(highs, lows, closes, self.config.period)
        if m != m or b != b:
            return 0
        if m > self.config.threshold and b > 0:
            return 1
        if m < -self.config.threshold and b > 0:
            return -1
        return 0
