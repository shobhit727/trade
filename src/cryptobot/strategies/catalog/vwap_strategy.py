"""Vwap reversion"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import vwap
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class VwapConfig:
    period: int = 20
    threshold: float = 0.01
    quantity: Decimal = Decimal("1")


class VwapStrategy(SignalStrategy):
    name = "vwap"

    def __init__(self, config: VwapConfig | None = None):
        super().__init__(config or VwapConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        v = vwap(closes, volumes)
        if v != v:
            return 0
        dev = (closes[-1] - v) / v
        if dev > self.config.threshold:
            return -1
        if dev < -self.config.threshold:
            return 1
        return 0
