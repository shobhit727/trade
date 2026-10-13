"""Spot-futures spread.

Two dead moves fixed here:

* an SMA was computed purely as a NaN guard and then discarded — removed;
* :func:`cryptobot.strategies.indicators.zscore` takes no period, so the window
  was silently the whole 300-bar buffer instead of `period` (measured z of 2.15
  vs 0.92 for the implied 30-bar z). The window now follows `period`.

Sign convention is unchanged: a stretched-*high* price zscore shorts, a
stretched-low one buys.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class SpotFuturesConfig:
    period: int = 30
    entry: float = 1.0
    quantity: Decimal = Decimal("1")


def _zscore(values, period: int) -> float:
    """Z-score of the last value over the trailing `period`-bar window.

    Same population-std convention as `indicators.zscore`, but with an explicit
    window length.
    """
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


class SpotFuturesStrategy(SignalStrategy):
    name = "spot_futures"

    def __init__(self, config: SpotFuturesConfig | None = None):
        super().__init__(config or SpotFuturesConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        z = _zscore(closes, self.config.period)
        if z != z:
            return 0
        if z > self.config.entry:
            return -1
        if z < -self.config.entry:
            return 1
        return 0
