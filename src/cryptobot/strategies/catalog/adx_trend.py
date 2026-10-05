"""Adx trend strength"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import atr
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class AdxTrendConfig:
    period: int = 14
    quantity: Decimal = Decimal("1")


class AdxTrendStrategy(SignalStrategy):
    name = "adx_trend"

    def __init__(self, config: AdxTrendConfig | None = None):
        super().__init__(config or AdxTrendConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        a = atr(highs, lows, closes, self.config.period)
        if a != a and len(closes) < self.config.period + 2:
            return 0
        return 1 if closes[-1] > closes[-2] else -1
