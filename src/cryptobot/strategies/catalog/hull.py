"""Hull moving average"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import hull
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class HullConfig:
    period: int = 20
    quantity: Decimal = Decimal("1")


class HullStrategy(SignalStrategy):
    name = "hull"

    def __init__(self, config: HullConfig | None = None):
        super().__init__(config or HullConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        h = hull(closes, self.config.period)
        if h != h:
            return 0
        return 1 if closes[-1] > h else -1
