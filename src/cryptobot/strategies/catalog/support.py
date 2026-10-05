"""Support breakdown"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import donchian_low
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class SupportConfig:
    period: int = 20
    quantity: Decimal = Decimal("1")


class SupportStrategy(SignalStrategy):
    name = "support"

    def __init__(self, config: SupportConfig | None = None):
        super().__init__(config or SupportConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        ll = donchian_low(lows, self.config.period)
        if ll != ll:
            return 0
        return -1 if closes[-1] <= ll else 0
