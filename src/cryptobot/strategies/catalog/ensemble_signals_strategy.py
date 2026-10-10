"""Ensemble signals"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import ema, rsi, sma
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class EnsembleSignalsConfig:
    period: int = 20
    rsip: int = 14
    min_votes: int = 2
    quantity: Decimal = Decimal("1")


class EnsembleSignalsStrategy(SignalStrategy):
    name = "ensemble_signals"

    def __init__(self, config: EnsembleSignalsConfig | None = None):
        super().__init__(config or EnsembleSignalsConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        votes = 0
        if sma(closes, self.config.period) != sma(closes, self.config.period):
            votes += 0
        if closes[-1] > sma(closes, self.config.period):
            votes += 1
        else:
            votes -= 1
        if closes[-1] > ema(closes, self.config.period):
            votes += 1
        else:
            votes -= 1
        r = rsi(closes, self.config.rsip)
        if r != r:
            return 0
        if r > 55:
            votes += 1
        elif r < 45:
            votes -= 1
        return 1 if votes >= self.config.min_votes else (-1 if votes <= -self.config.min_votes else 0)
