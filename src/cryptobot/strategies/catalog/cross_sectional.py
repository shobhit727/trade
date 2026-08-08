'''Cross-sectional momentum'''

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import roc
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class CrossSectionalConfig:
    period: int = 20
    threshold: float = 0.015
    quantity: Decimal = Decimal("1")


class CrossSectionalStrategy(SignalStrategy):
    name = "cross_sectional"

    def __init__(self, config: CrossSectionalConfig | None = None):
        super().__init__(config or CrossSectionalConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        m = roc(closes, self.config.period)
        if m != m:
            return 0
        return 1 if m > self.config.threshold else (-1 if m < -self.config.threshold else 0)
