'''Bollinger squeeze'''

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import sma, roc
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class SqueezeConfig:
    period: int = 20
    squeeze_vol: float = 0.05
    quantity: Decimal = Decimal("1")


class SqueezeStrategy(SignalStrategy):
    name = "squeeze"

    def __init__(self, config: SqueezeConfig | None = None):
        super().__init__(config or SqueezeConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        import numpy as _np
        m = sma(closes, self.config.period)
        if m != m or m == 0:
            return 0
        band_w = float(_np.std(closes[-self.config.period:])) / m
        r = roc(closes, 3)
        if r != r:
            return 0
        if band_w < self.config.squeeze_vol and r > 0:
            return 1
        if band_w < self.config.squeeze_vol and r < 0:
            return -1
        return 0
