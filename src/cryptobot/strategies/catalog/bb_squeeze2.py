"""Bollinger squeeze v2"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import roc, sma
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class BbSqueeze2Config:
    period: int = 20
    threshold: float = 0.05
    quantity: Decimal = Decimal("1")


class BbSqueeze2Strategy(SignalStrategy):
    name = "bb_squeeze2"

    def __init__(self, config: BbSqueeze2Config | None = None):
        super().__init__(config or BbSqueeze2Config())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        import numpy as _np

        m = sma(closes, self.config.period)
        if m != m or m == 0 or len(closes) < self.config.period:
            return 0
        std = float(_np.std(closes[-self.config.period :])) / m
        r = roc(closes, 3)
        if r != r:
            return 0
        if std < self.config.threshold and r > 0:
            return 1
        if std < self.config.threshold and r < 0:
            return -1
        return 0
