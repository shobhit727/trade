"""Double exponential ma"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import dema
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class DemaConfig:
    period: int = 20
    quantity: Decimal = Decimal("1")


class DemaStrategy(SignalStrategy):
    name = "dema"

    def __init__(self, config: DemaConfig | None = None):
        super().__init__(config or DemaConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        d = dema(closes, self.config.period)
        if d != d:
            return 0
        return 1 if closes[-1] > d else -1
