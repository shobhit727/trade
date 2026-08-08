'''Stochastic reversal'''

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import stochastic
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class StochasticConfig:
    period: int = 14
    lower: float = 20.0
    upper: float = 80.0
    quantity: Decimal = Decimal("1")


class StochasticStrategy(SignalStrategy):
    name = "stochastic"

    def __init__(self, config: StochasticConfig | None = None):
        super().__init__(config or StochasticConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        k = stochastic(closes, highs, lows, self.config.period)
        if k != k:
            return 0
        if k <= self.config.lower:
            return 1
        if k >= self.config.upper:
            return -1
        return 0
