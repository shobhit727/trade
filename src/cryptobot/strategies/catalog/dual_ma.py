'''Dual moving average'''

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import ema
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class DualMaConfig:
    fast: int = 20
    slow: int = 50
    quantity: Decimal = Decimal("1")


class DualMaStrategy(SignalStrategy):
    name = "dual_ma"

    def __init__(self, config: DualMaConfig | None = None):
        super().__init__(config or DualMaConfig())

    def warmup(self, closes) -> int:
        return self.config.slow

    def signal(self, closes, highs, lows, volumes):
        f = ema(closes, self.config.fast)
        s = ema(closes, self.config.slow)
        if f != f or s != s or f == s:
            return 0
        return 1 if f > s else -1
