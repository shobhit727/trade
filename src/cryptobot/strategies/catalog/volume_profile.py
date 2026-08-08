"""Volume profile momentum"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import sma
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class VolumeProfileConfig:
    period: int = 20
    threshold: float = 0.005
    quantity: Decimal = Decimal("1")


class VolumeProfileStrategy(SignalStrategy):
    name = "volume_profile"

    def __init__(self, config: VolumeProfileConfig | None = None):
        super().__init__(config or VolumeProfileConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        if len(closes) < self.config.period:
            return 0
        m = sma(closes, self.config.period)
        if m != m or m == 0:
            return 0
        dev = (closes[-1] - m) / m
        return 1 if dev > self.config.threshold else (-1 if dev < -self.config.threshold else 0)
