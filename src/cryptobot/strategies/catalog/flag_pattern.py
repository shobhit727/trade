"""Flag / pennant continuation pattern.

Geometry is governed entirely by ``config.period`` (``p`` bars per leg), which
the previous version ignored (it hard-coded a 3-bar rising/falling chain):

  1. POLE      the ``p`` bars ending at ``-(p+1)``  -> net move sets direction
  2. FLAG      the ``p`` bars ending at ``-1``      -> must consolidate: its
               high-low range must be tighter than the pole's range
  3. BREAKOUT  the current close must clear the flag's prior extreme

Signal is +1 on an upside breakout out of an up-pole, -1 on the mirror, else
flat. A pole without a consolidation, or a breakout that is not preceded by
one, does not signal.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class FlagConfig:
    period: int = 5
    quantity: Decimal = Decimal("1")


class FlagStrategy(SignalStrategy):
    name = "flag"

    def __init__(self, config: FlagConfig | None = None):
        super().__init__(config or FlagConfig())

    def warmup(self, closes) -> int:
        # pole (period) + flag (period) + the breakout bar
        return 2 * self.config.period + 1

    def signal(self, closes, highs, lows, volumes):
        p = self.config.period
        if len(closes) < 2 * p + 1 or len(highs) < 2 * p + 1 or len(lows) < 2 * p + 1:
            return 0

        # 1. pole: the p bars preceding the flag (today excluded)
        pole_closes = closes[-2 * p - 1 : -p - 1]
        pole_highs = highs[-2 * p - 1 : -p - 1]
        pole_lows = lows[-2 * p - 1 : -p - 1]
        pole_move = pole_closes[-1] - pole_closes[0]
        if pole_move == 0:
            return 0
        pole_range = max(pole_highs) - min(pole_lows)
        if pole_range <= 0:
            return 0

        # 2. flag: the p bars before today must be tighter than the pole
        flag_highs = highs[-p - 1 : -1]
        flag_lows = lows[-p - 1 : -1]
        flag_range = max(flag_highs) - min(flag_lows)
        if flag_range >= pole_range:
            return 0

        # 3. breakout beyond the flag's prior extreme
        if pole_move > 0 and closes[-1] > max(flag_highs):
            return 1
        if pole_move < 0 and closes[-1] < min(flag_lows):
            return -1
        return 0
