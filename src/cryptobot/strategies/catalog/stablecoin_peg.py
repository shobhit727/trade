"""Stablecoin peg band"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import sma
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class StablecoinPegConfig:
    period: int = 60
    entry: float = 2.0
    quantity: Decimal = Decimal("1")


class StablecoinPegStrategy(SignalStrategy):
    name = "stablecoin_peg"

    def __init__(self, config: StablecoinPegConfig | None = None):
        super().__init__(config or StablecoinPegConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        m = sma(closes, self.config.period)
        if m != m or m == 0:
            return 0
        dev = (closes[-1] - m) / m
        if dev > 0.005:
            return -1
        if dev < -0.005:
            return 1
        return 0
