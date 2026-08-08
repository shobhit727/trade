'''Moving average crossover'''

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import sma
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class MaCrossConfig:
    fast: int = 10
    slow: int = 30
    quantity: Decimal = Decimal("1")


class MaCrossStrategy(SignalStrategy):
    name = "ma_cross"

    def __init__(self, config: MaCrossConfig | None = None):
        super().__init__(config or MaCrossConfig())

    def warmup(self, closes) -> int:
        return self.config.slow

    def signal(self, closes, highs, lows, volumes):
        f = sma(closes, self.config.fast)
        s = sma(closes, self.config.slow)
        if f != f or s != s or f == s:
            return 0
        return 1 if f > s else -1
