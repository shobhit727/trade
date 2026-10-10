"""Volume momentum"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import obv, roc
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class VolumeMomentumConfig:
    period: int = 20
    threshold: float = 0.01
    quantity: Decimal = Decimal("1")


class VolumeMomentumStrategy(SignalStrategy):
    name = "volume_momentum"

    def __init__(self, config: VolumeMomentumConfig | None = None):
        super().__init__(config or VolumeMomentumConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        m = roc(closes, self.config.period)
        def_sig = obv(closes, volumes)
        if m != m:
            return 0
        if m > self.config.threshold and def_sig > 0:
            return 1
        if m < -self.config.threshold and def_sig < 0:
            return -1
        return 0
