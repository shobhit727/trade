"""Volume weighted momentum"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import roc
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class VwMomentumConfig:
    period: int = 20
    threshold: float = 0.01
    quantity: Decimal = Decimal("1")


class VwMomentumStrategy(SignalStrategy):
    name = "vw_momentum"

    def __init__(self, config: VwMomentumConfig | None = None):
        super().__init__(config or VwMomentumConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        m = roc(closes, self.config.period)
        if m != m:
            return 0
        avg = (
            sum(volumes[-self.config.period :]) / self.config.period
            if len(volumes) >= self.config.period
            else 0
        )
        vw = avg * (1.0 if volumes[-1] >= avg else 0.5)
        if m > self.config.threshold and vw > 0:
            return 1
        if m < -self.config.threshold and vw > 0:
            return -1
        return 0
