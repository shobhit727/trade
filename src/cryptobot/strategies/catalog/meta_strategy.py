"""Meta-strategy trend gate"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import sma
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class MetaStrategyConfig:
    period: int = 20
    quantity: Decimal = Decimal("1")


class MetaStrategy(SignalStrategy):
    name = "meta"

    def __init__(self, config: MetaStrategyConfig | None = None):
        super().__init__(config or MetaStrategyConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        t = sma(closes, self.config.period)
        if t != t:
            return 0
        return 1 if closes[-1] > t else -1
