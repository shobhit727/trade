"""Volatility scaling"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import atr
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class VolScalingConfig:
    period: int = 14
    min_vol: float = 0.001
    quantity: Decimal = Decimal("1")


class VolScalingStrategy(SignalStrategy):
    name = "vol_scaling"

    def __init__(self, config: VolScalingConfig | None = None):
        super().__init__(config or VolScalingConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        b = atr(highs, lows, closes, self.config.period)
        if b != b:
            return 0
        if b / max(closes[-1], 1e-9) > self.config.min_vol and closes[-1] > closes[-2]:
            return 1
        if b / max(closes[-1], 1e-9) > self.config.min_vol and closes[-1] < closes[-2]:
            return -1
        return 0
