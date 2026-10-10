"""Liquidation hunt"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import atr
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class LiquidationHuntConfig:
    period: int = 14
    multiplier: float = 2.0
    quantity: Decimal = Decimal("1")


class LiquidationHuntStrategy(SignalStrategy):
    name = "liquidation_hunt"

    def __init__(self, config: LiquidationHuntConfig | None = None):
        super().__init__(config or LiquidationHuntConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        b = atr(highs, lows, closes, self.config.period)
        if b != b:
            return 0
        return 1 if closes[-1] > closes[-2] and b > 0 else -1
