"""Gaussian (z-score) reversion.

The z-score is taken over the last ``config.period`` bars only:

    z = (close_t - mean(last period closes)) / std(last period closes)

The previous version called ``zscore(closes)`` on the whole 300-bar rolling
buffer, so ``period`` was decorative and the statistic was a hard-coded 300-bar
z-score regardless of configuration. The window is now the config.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class GaussianConfig:
    period: int = 30
    entry: float = 0.8
    quantity: Decimal = Decimal("1")


class GaussianStrategy(SignalStrategy):
    name = "gaussian"

    def __init__(self, config: GaussianConfig | None = None):
        super().__init__(config or GaussianConfig())

    def warmup(self, closes) -> int:
        return self.config.period + 1

    def signal(self, closes, highs, lows, volumes):
        period = self.config.period
        if len(closes) < period:
            return 0
        window = closes[-period:]
        mean = sum(window) / period
        var = sum((c - mean) ** 2 for c in window) / period
        sd = var**0.5
        if sd == 0:
            return 0
        z = (closes[-1] - mean) / sd
        if z >= self.config.entry:
            return -1
        if z <= -self.config.entry:
            return 1
        return 0
