'''Opening range breakout'''

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import donchian_high, donchian_low
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class OpenRangeConfig:
    period: int = 15
    quantity: Decimal = Decimal("1")


class OpenRangeStrategy(SignalStrategy):
    name = "open_range"

    def __init__(self, config: OpenRangeConfig | None = None):
        super().__init__(config or OpenRangeConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        hh = donchian_high(highs[: self.config.period], len(highs[: self.config.period]))
        ll = donchian_low(lows[: self.config.period], len(lows[: self.config.period]))
        if hh != hh:
            return 0
        if len(closes) >= self.config.period and closes[-1] >= hh:
            return 1
        if len(closes) >= self.config.period and closes[-1] <= ll:
            return -1
        return 0
