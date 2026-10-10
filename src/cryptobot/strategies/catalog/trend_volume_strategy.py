"""Trend + volume filter"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import sma
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class TrendVolumeConfig:
    period: int = 20
    vol_ratio: float = 1.2
    quantity: Decimal = Decimal("1")


class TrendVolumeStrategy(SignalStrategy):
    name = "trend_volume"

    def __init__(self, config: TrendVolumeConfig | None = None):
        super().__init__(config or TrendVolumeConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        t = sma(closes, self.config.period)
        if t != t or len(volumes) < self.config.period:
            return 0
        avg = sum(volumes[-self.config.period :]) / self.config.period
        if closes[-1] > t and volumes[-1] > avg * self.config.vol_ratio:
            return 1
        if closes[-1] < t and volumes[-1] > avg * self.config.vol_ratio:
            return -1
        return 0
