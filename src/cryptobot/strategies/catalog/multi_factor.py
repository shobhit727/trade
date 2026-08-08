"""Multi-factor"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import rsi, sma
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class MultiFactorConfig:
    period: int = 20
    rsip: int = 14
    quantity: Decimal = Decimal("1")


class MultiFactorStrategy(SignalStrategy):
    name = "multi_factor"

    def __init__(self, config: MultiFactorConfig | None = None):
        super().__init__(config or MultiFactorConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        t = sma(closes, self.config.period)
        r = rsi(closes, self.config.rsip)
        if t != t or r != r:
            return 0
        score = (1 if closes[-1] > t else -1) + (1 if r > 50 else -1)
        return 1 if score >= 2 else (-1 if score <= -2 else 0)
