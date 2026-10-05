"""Anchored vwap"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import vwap
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class AnchoredVwapConfig:
    period: int = 50
    threshold: float = 0.02
    quantity: Decimal = Decimal("1")


class AnchoredVwapStrategy(SignalStrategy):
    name = "anchored_vwap"

    def __init__(self, config: AnchoredVwapConfig | None = None):
        super().__init__(config or AnchoredVwapConfig())

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
