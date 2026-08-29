"""Kaufman adaptive ma"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import kama
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class KamaConfig:
    period: int = 20
    quantity: Decimal = Decimal("1")


class KamaStrategy(SignalStrategy):
    name = "kama"

    def __init__(self, config: KamaConfig | None = None):
        super().__init__(config or KamaConfig())

    def warmup(self, closes) -> int:
        return self.config.period + 1

    def signal(self, closes, highs, lows, volumes):
        e = kama(closes, self.config.period)
        if e != e:
            return 0
        return 1 if closes[-1] > e else -1
