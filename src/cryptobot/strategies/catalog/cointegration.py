"""Cointegration break"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import zscore
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class CointegrationConfig:
    period: int = 30
    entry: float = 1.0
    quantity: Decimal = Decimal("1")


class CointegrationStrategy(SignalStrategy):
    name = "cointegration"

    def __init__(self, config: CointegrationConfig | None = None):
        super().__init__(config or CointegrationConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        z = zscore(closes)
        if z != z or len(closes) < self.config.period:
            return 0
        if z > self.config.entry:
            return -1
        if z < -self.config.entry:
            return 1
        return 0
