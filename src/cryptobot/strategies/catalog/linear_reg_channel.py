'''Linear regression channel'''

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import sma
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class LinearRegChannelConfig:
    period: int = 20
    quantity: Decimal = Decimal("1")


class LinearRegChannelStrategy(SignalStrategy):
    name = "linear_reg_channel"

    def __init__(self, config: LinearRegChannelConfig | None = None):
        super().__init__(config or LinearRegChannelConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        m = sma(closes, self.config.period)
        if m != m:
            return 0
        return 1 if closes[-1] > m else -1
