"""Volatility targeting"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import atr
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class VolTargetConfig:
    period: int = 14
    target: float = 0.01
    quantity: Decimal = Decimal("1")


class VolTargetStrategy(SignalStrategy):
    name = "vol_target"

    def __init__(self, config: VolTargetConfig | None = None):
        super().__init__(config or VolTargetConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        b = atr(highs, lows, closes, self.config.period)
        if b != b:
            return 0
        if closes[-1] > closes[-2] and b / max(closes[-1], 1e-9) < self.config.target * 2:
            return 1
        if closes[-1] < closes[-2] and b / max(closes[-1], 1e-9) < self.config.target * 2:
            return -1
        return 0
