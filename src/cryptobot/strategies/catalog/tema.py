"""Triple exponential ma"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import tema
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class TemaConfig:
    period: int = 20
    quantity: Decimal = Decimal("1")


class TemaStrategy(SignalStrategy):
    name = "tema"

    def __init__(self, config: TemaConfig | None = None):
        super().__init__(config or TemaConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        t = tema(closes, self.config.period)
        if t != t:
            return 0
        return 1 if closes[-1] > t else -1
