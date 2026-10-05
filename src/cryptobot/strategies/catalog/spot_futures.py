"""Spot-futures spread"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import sma, zscore
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class SpotFuturesConfig:
    period: int = 30
    entry: float = 1.0
    quantity: Decimal = Decimal("1")


class SpotFuturesStrategy(SignalStrategy):
    name = "spot_futures"

    def __init__(self, config: SpotFuturesConfig | None = None):
        super().__init__(config or SpotFuturesConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        z = zscore(closes)
        m = sma(closes, self.config.period)
        if z != z or m != m:
            return 0
        if z > self.config.entry:
            return -1
        if z < -self.config.entry:
            return 1
        return 0
