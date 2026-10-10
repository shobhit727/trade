"""Obv momentum"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import obv
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class ObvConfig:
    period: int = 20
    quantity: Decimal = Decimal("1")


class ObvStrategy(SignalStrategy):
    name = "obv"

    def __init__(self, config: ObvConfig | None = None):
        super().__init__(config or ObvConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        if len(closes) < 2:
            return 0
        o = obv(closes, volumes)
        prev = obv(closes[:-1], volumes[:-1])
        if o != o or prev != prev:
            return 0
        if o > prev:
            return 1
        if o < prev:
            return -1
        return 0
