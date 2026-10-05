"""Atr breakout"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import atr, sma
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class AtrBreakoutConfig:
    period: int = 14
    multiplier: float = 1.5
    quantity: Decimal = Decimal("1")


class AtrBreakoutStrategy(SignalStrategy):
    name = "atr_breakout"

    def __init__(self, config: AtrBreakoutConfig | None = None):
        super().__init__(config or AtrBreakoutConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        b = atr(highs, lows, closes, self.config.period)
        m = sma(closes, self.config.period)
        if b != b or m != m:
            return 0
        if closes[-1] > m + b * self.config.multiplier:
            return 1
        if closes[-1] < m - b * self.config.multiplier:
            return -1
        return 0
