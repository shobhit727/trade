"""Donchian channel breakout.

The channel is built from the ``period`` bars **before** the current one, so a
breakout is a genuine breakout:

    hh = max(highs[-period-1:-1])     ll = min(lows[-period-1:-1])
    +1 when close > hh, -1 when close < ll, else flat

Including the current bar (``max(highs[-period:])``) makes ``close >= hh`` true
only when the close sits exactly on the day's high — on NSE daily data that
fired on 0.25% of bars (0.00% on one training window), i.e. the strategy was
effectively inert. Excluding it restores a fire rate of a few percent.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class DonchianConfig:
    period: int = 20
    quantity: Decimal = Decimal("1")


class DonchianStrategy(SignalStrategy):
    name = "donchian"

    def __init__(self, config: DonchianConfig | None = None):
        super().__init__(config or DonchianConfig())

    def warmup(self, closes) -> int:
        # period prior bars plus the bar being evaluated
        return self.config.period + 1

    def signal(self, closes, highs, lows, volumes):
        p = self.config.period
        if len(highs) < p + 1 or len(lows) < p + 1:
            return 0
        # Exclude the current bar: highs[-p-1:-1] is the p bars ending at t-1.
        prior_highs = highs[-p - 1 : -1]
        prior_lows = lows[-p - 1 : -1]
        hh = max(prior_highs)
        ll = min(prior_lows)
        if closes[-1] > hh:
            return 1
        if closes[-1] < ll:
            return -1
        return 0
