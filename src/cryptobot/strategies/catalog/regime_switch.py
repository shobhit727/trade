"""Regime switch"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import atr, sma
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class RegimeSwitchConfig:
    period: int = 20
    adx_p: int = 14
    quantity: Decimal = Decimal("1")


class RegimeSwitchStrategy(SignalStrategy):
    name = "regime_switch"

    def __init__(self, config: RegimeSwitchConfig | None = None):
        super().__init__(config or RegimeSwitchConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        t = sma(closes, self.config.period)
        b = atr(highs, lows, closes, self.config.adx_p)
        if t != t or b != b:
            return 0
        up = closes[-1] > t
        if up and closes[-1] > closes[-2]:
            return 1
        if not up and closes[-1] < closes[-2]:
            return -1
        return 0
