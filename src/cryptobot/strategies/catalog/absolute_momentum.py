"""Absolute momentum"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import roc
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class AbsoluteMomentumConfig:
    period: int = 30
    threshold: float = 0.0
    quantity: Decimal = Decimal("1")


class AbsoluteMomentumStrategy(SignalStrategy):
    name = "absolute_momentum"

    def __init__(self, config: AbsoluteMomentumConfig | None = None):
        super().__init__(config or AbsoluteMomentumConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        m = roc(closes, self.config.period)
        if m != m:
            return 0
        return 1 if m > self.config.threshold else (-1 if m < -self.config.threshold else 0)
