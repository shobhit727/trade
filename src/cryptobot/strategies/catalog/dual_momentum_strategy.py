"""Dual momentum"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import ema
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class DualMomentumConfig:
    fast: int = 10
    slow: int = 30
    quantity: Decimal = Decimal("1")


class DualMomentumStrategy(SignalStrategy):
    name = "dual_momentum"

    def __init__(self, config: DualMomentumConfig | None = None):
        super().__init__(config or DualMomentumConfig())

    def warmup(self, closes) -> int:
        return self.config.slow

    def signal(self, closes, highs, lows, volumes):
        f = ema(closes, self.config.fast)
        s = ema(closes, self.config.slow)
        if f != f or s != s or f == s:
            return 0
        return 1 if f > s else -1
