"""Chaikin money flow"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import chaikin_mf
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class CmfConfig:
    period: int = 20
    upper: float = 0.1
    lower: float = -0.1
    quantity: Decimal = Decimal("1")


class CmfStrategy(SignalStrategy):
    name = "cmf"

    def __init__(self, config: CmfConfig | None = None):
        super().__init__(config or CmfConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        cmf = chaikin_mf(closes, highs, lows, volumes, self.config.period)
        if cmf != cmf:
            return 0
        if cmf > self.config.upper:
            return 1
        if cmf < self.config.lower:
            return -1
        return 0
