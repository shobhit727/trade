"""Resistance breakout"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import donchian_high
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class ResistanceConfig:
    period: int = 20
    quantity: Decimal = Decimal("1")


class ResistanceStrategy(SignalStrategy):
    name = "resistance"

    def __init__(self, config: ResistanceConfig | None = None):
        super().__init__(config or ResistanceConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        hh = donchian_high(highs, self.config.period)
        if hh != hh:
            return 0
        return 1 if closes[-1] >= hh else 0
