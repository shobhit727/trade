"""Correlation gate"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import roc, sma
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class CorrGateConfig:
    period: int = 20
    threshold: float = 0.01
    quantity: Decimal = Decimal("1")


class CorrGateStrategy(SignalStrategy):
    name = "corr_gate"

    def __init__(self, config: CorrGateConfig | None = None):
        super().__init__(config or CorrGateConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        m = sma(closes, self.config.period)
        r = roc(closes, self.config.period)
        if m != m or r != r:
            return 0
        if r > self.config.threshold and closes[-1] > m:
            return 1
        if r < -self.config.threshold and closes[-1] < m:
            return -1
        return 0
