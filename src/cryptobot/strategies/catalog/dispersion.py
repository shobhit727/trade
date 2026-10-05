"""Dispersion trend"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import sma, zscore
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class DispersionConfig:
    period: int = 30
    entry: float = 1.0
    quantity: Decimal = Decimal("1")


class DispersionStrategy(SignalStrategy):
    name = "dispersion"

    def __init__(self, config: DispersionConfig | None = None):
        super().__init__(config or DispersionConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        z = zscore(closes)
        m = sma(closes, self.config.period)
        if z != z or m != m:
            return 0
        if z >= self.config.entry and closes[-1] > m:
            return 1
        if z <= -self.config.entry and closes[-1] < m:
            return -1
        return 0
