"""Garch classic"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import atr
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class GarchClassicConfig:
    period: int = 14
    multiplier: float = 1.2
    quantity: Decimal = Decimal("1")


class GarchClassicStrategy(SignalStrategy):
    name = "garch_classic"

    def __init__(self, config: GarchClassicConfig | None = None):
        super().__init__(config or GarchClassicConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        b = atr(highs, lows, closes, self.config.period)
        prev = atr(highs[:-1], lows[:-1], closes[:-1], self.config.period)
        if b != b or prev != prev or prev == 0:
            return 0
        if b / prev > self.config.multiplier:
            return 1 if closes[-1] > closes[-2] else -1
        return 0
