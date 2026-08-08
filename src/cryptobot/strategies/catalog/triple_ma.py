'''Triple moving average'''

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import sma
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class TripleMaConfig:
    fast: int = 5
    mid: int = 15
    slow: int = 30
    quantity: Decimal = Decimal("1")


class TripleMaStrategy(SignalStrategy):
    name = "triple_ma"

    def __init__(self, config: TripleMaConfig | None = None):
        super().__init__(config or TripleMaConfig())

    def warmup(self, closes) -> int:
        return self.config.slow

    def signal(self, closes, highs, lows, volumes):
        f = sma(closes, self.config.fast)
        m = sma(closes, self.config.mid)
        s = sma(closes, self.config.slow)
        if any(v != v for v in (f, m, s)):
            return 0
        if f > m > s:
            return 1
        if f < m < s:
            return -1
        return 0
