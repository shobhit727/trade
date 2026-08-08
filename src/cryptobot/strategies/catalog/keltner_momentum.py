"""Keltner momentum"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import atr, keltner_mid
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class KeltnerMomentumConfig:
    period: int = 20
    multiplier: float = 2.0
    quantity: Decimal = Decimal("1")


class KeltnerMomentumStrategy(SignalStrategy):
    name = "keltner_momentum"

    def __init__(self, config: KeltnerMomentumConfig | None = None):
        super().__init__(config or KeltnerMomentumConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        mid = keltner_mid(closes, self.config.period)
        b = atr(highs, lows, closes, self.config.period)
        if mid != mid or b != b:
            return 0
        if closes[-1] > mid + self.config.multiplier * b:
            return 1
        if closes[-1] < mid - self.config.multiplier * b:
            return -1
        return 0
