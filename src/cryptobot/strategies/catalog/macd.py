"""Macd"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import macd, macd_signal
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class MacdConfig:
    fast: int = 12
    slow: int = 26
    signal: int = 9
    quantity: Decimal = Decimal("1")


class MacdStrategy(SignalStrategy):
    name = "macd"

    def __init__(self, config: MacdConfig | None = None):
        super().__init__(config or MacdConfig())

    def warmup(self, closes) -> int:
        return self.config.slow

    def signal(self, closes, highs, lows, volumes):
        line = macd(closes, self.config.fast, self.config.slow)
        sig = macd_signal(closes, self.config.fast, self.config.slow, self.config.signal)
        if line != line or sig != sig or line == sig:
            return 0
        return 1 if line > sig else -1
