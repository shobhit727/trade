"""Volume spike"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class VolumeSpikeConfig:
    period: int = 20
    mult: float = 2.0
    quantity: Decimal = Decimal("1")


class VolumeSpikeStrategy(SignalStrategy):
    name = "volume_spike"

    def __init__(self, config: VolumeSpikeConfig | None = None):
        super().__init__(config or VolumeSpikeConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        if len(volumes) < self.config.period:
            return 0
        avg = sum(volumes[-self.config.period : -1]) / (self.config.period - 1)
        if avg <= 0 or volumes[-1] > avg * self.config.mult and closes[-1] > closes[-2]:
            return 1
        return 0
