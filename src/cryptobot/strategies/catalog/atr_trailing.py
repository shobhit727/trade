"""Atr trailing"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import atr, sma
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class AtrTrailingConfig:
    period: int = 14
    multiplier: float = 2.0
    quantity: Decimal = Decimal("1")


class AtrTrailingStrategy(SignalStrategy):
    name = "atr_trailing"

    def __init__(self, config: AtrTrailingConfig | None = None):
        super().__init__(config or AtrTrailingConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        b = atr(highs, lows, closes, self.config.period)
        if b != b:
            return 0
        m = sma(closes, self.config.period)
        if m != m:
            return 0
        return (
            1
            if closes[-1] > m + b * self.config.multiplier
            else (-1 if closes[-1] < m - b * self.config.multiplier else 0)
        )
