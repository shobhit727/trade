"""Cumulative delta"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import cumulative_delta
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class CumulativeDeltaConfig:
    window: int = 30
    quantity: Decimal = Decimal("1")


class CumulativeDeltaStrategy(SignalStrategy):
    name = "cumulative_delta"

    def __init__(self, config: CumulativeDeltaConfig | None = None):
        super().__init__(config or CumulativeDeltaConfig())

    def warmup(self, closes) -> int:
        return self.config.window

    def signal(self, closes, highs, lows, volumes):
        d = cumulative_delta(closes, volumes, self.config.window)
        if d != d:
            return 0
        return 1 if d > 0 else (-1 if d < 0 else 0)
