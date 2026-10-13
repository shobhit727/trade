"""Volume weighted momentum.

The old signal multiplied a positive mean volume by `1.0` or `0.5` and then
tested `vw > 0` — which is just `avg_volume > 0`, so the branch was dead.
Replacing the volume series with a constant changed zero cells.

The signal is now the **volume-weighted ROC**: the ratio of the volume-weighted
average price over the last `period` bars to the volume-weighted average price
over the `period` bars before that, minus one. Heavy-volume bars pull the
reference level, so the momentum reading is the one an investor could actually
have executed — unlike the plain close-to-close ROC it replaces.

With constant volume the two coincide with the ratio of two simple moving
averages, so `threshold` keeps the same units and its default (0.01) still
trades. `warmup` now needs `2 * period + 1` bars (two adjacent windows).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class VwMomentumConfig:
    period: int = 20
    threshold: float = 0.01
    quantity: Decimal = Decimal("1")


def _vwap(closes, volumes, start: int, stop: int) -> float:
    """Volume-weighted average close over ``closes[start:stop]``."""
    pv = 0.0
    vv = 0.0
    for i in range(start, stop):
        v = volumes[i]
        pv += closes[i] * v
        vv += v
    if vv <= 0:
        return float("nan")
    return pv / vv


def _vw_roc(closes, volumes, period: int) -> float:
    """Volume-weighted rate of change over ``period`` bars (NaN if undefined)."""
    n = len(closes)
    if period < 1 or n < 2 * period + 1 or len(volumes) < n:
        return float("nan")
    now = _vwap(closes, volumes, n - period, n)
    then = _vwap(closes, volumes, n - 2 * period, n - period)
    if now != now or then != then or then == 0:
        return float("nan")
    return now / then - 1.0


class VwMomentumStrategy(SignalStrategy):
    name = "vw_momentum"

    def __init__(self, config: VwMomentumConfig | None = None):
        super().__init__(config or VwMomentumConfig())

    def warmup(self, closes) -> int:
        return 2 * self.config.period + 1

    def signal(self, closes, highs, lows, volumes):
        m = _vw_roc(closes, volumes, self.config.period)
        if m != m:
            return 0
        if m > self.config.threshold:
            return 1
        if m < -self.config.threshold:
            return -1
        return 0
