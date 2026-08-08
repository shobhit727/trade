"""Adaptive allocation"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import roc
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class AdaptiveAllocationConfig:
    period: int = 20
    threshold: float = 0.005
    quantity: Decimal = Decimal("1")


class AdaptiveAllocationStrategy(SignalStrategy):
    name = "adaptive_allocation"

    def __init__(self, config: AdaptiveAllocationConfig | None = None):
        super().__init__(config or AdaptiveAllocationConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        m = roc(closes, self.config.period)
        if m != m:
            return 0
        if m > self.config.threshold:
            return 1
        if m < -self.config.threshold:
            return -1
        return 0
