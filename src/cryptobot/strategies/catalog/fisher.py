'''Fisher transform'''

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import fisher_transform
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class FisherConfig:
    period: int = 10
    entry: float = 0.5
    quantity: Decimal = Decimal("1")


class FisherStrategy(SignalStrategy):
    name = "fisher"

    def __init__(self, config: FisherConfig | None = None):
        super().__init__(config or FisherConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        f = fisher_transform(closes, self.config.period)
        if f != f:
            return 0
        if f >= self.config.entry:
            return -1
        if f <= -self.config.entry:
            return 1
        return 0
