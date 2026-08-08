'''Bb reversion'''

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import bollinger_position
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class BollingerConfig:
    period: int = 20
    n_std: float = 2.0
    entry: float = 1.0
    quantity: Decimal = Decimal("1")


class BollingerStrategy(SignalStrategy):
    name = "bollinger"

    def __init__(self, config: BollingerConfig | None = None):
        super().__init__(config or BollingerConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        sig = bollinger_position(closes, self.config.period, self.config.n_std)
        if sig != sig:
            return 0
        if sig > self.config.entry:
            return -1
        if sig < -self.config.entry:
            return 1
        return 0
