'''Ema crossover'''

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import ema
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class EmaCrossConfig:
    fast: int = 12
    slow: int = 26
    quantity: Decimal = Decimal("1")


class EmaCrossStrategy(SignalStrategy):
    name = "ema_cross"

    def __init__(self, config: EmaCrossConfig | None = None):
        super().__init__(config or EmaCrossConfig())

    def warmup(self, closes) -> int:
        return self.config.slow

    def signal(self, closes, highs, lows, volumes):
        f = ema(closes, self.config.fast)
        s = ema(closes, self.config.slow)
        if f != f or s != s or f == s:
            return 0
        return 1 if f > s else -1
