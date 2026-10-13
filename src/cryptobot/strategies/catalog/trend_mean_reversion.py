"""Trend continuation.

Renamed from `trend_mean_reversion` / `trend_mr`. The rule was never mean
reversion: `z > entry AND close > SMA(slow)` fires when price is `entry` standard
deviations *above* its own mean **and** above its trend — it buys strength. The
rename is deliberate: flipping the sign to `z < -entry` would change the
strategy's behaviour without re-validating `research/agent_tmr/REPORT.md`, so the
name was corrected instead of the semantics.

Both signals were retained unchanged apart from one fix: `TrendMrConfig.period`
was dead — `signal()` never read it and the z-score window was whatever the
300-bar `deque` happened to hold. The window now follows `period`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import sma
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class TrendContinuationConfig:
    #: trend filter: price must also sit on the matching side of this SMA
    slow: int = 40
    #: z-score window (standard deviations over `period` bars)
    period: int = 20
    entry: float = 1.5
    quantity: Decimal = Decimal("1")


def _zscore(values, period: int) -> float:
    """Z-score of the last value over the trailing `period`-bar window."""
    if period < 1:
        return float("nan")
    w = values[-period:] if len(values) > period else values
    n = len(w)
    if n < 2:
        return float("nan")
    mean = sum(w) / n
    var = sum((x - mean) ** 2 for x in w) / n
    sd = var**0.5
    if sd == 0:
        return 0.0
    return (w[-1] - mean) / sd


class TrendContinuationStrategy(SignalStrategy):
    name = "trend_continuation"

    def __init__(self, config: TrendContinuationConfig | None = None):
        super().__init__(config or TrendContinuationConfig())

    def warmup(self, closes) -> int:
        return max(self.config.slow, self.config.period)

    def signal(self, closes, highs, lows, volumes):
        t = sma(closes, self.config.slow)
        z = _zscore(closes, self.config.period)
        if t != t or z != z:
            return 0
        if z > self.config.entry and closes[-1] > t:
            return 1
        if z < -self.config.entry and closes[-1] < t:
            return -1
        return 0


# Backwards-compatible aliases: the pre-rename names are still imported by
# `research/agent_tmr/` and `tests/strategies/test_catalog_trend_mr.py`.
TrendMrConfig = TrendContinuationConfig
TrendMrStrategy = TrendContinuationStrategy

__all__ = [
    "TrendContinuationConfig",
    "TrendContinuationStrategy",
    "TrendMrConfig",
    "TrendMrStrategy",
]
