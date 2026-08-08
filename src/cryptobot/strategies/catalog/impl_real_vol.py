"""Implied vs realized vol"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import atr
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class ImplRealVolConfig:
    period: int = 14
    threshold: float = 0.005
    quantity: Decimal = Decimal("1")


class ImplRealVolStrategy(SignalStrategy):
    name = "impl_real_vol"

    def __init__(self, config: ImplRealVolConfig | None = None):
        super().__init__(config or ImplRealVolConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        b = atr(highs, lows, closes, self.config.period)
        if b != b or closes[-1] <= 0:
            return 0
        rv = b / closes[-1]
        if rv > self.config.threshold and closes[-1] > closes[-2]:
            return 1
        if rv > self.config.threshold and closes[-1] < closes[-2]:
            return -1
        return 0
