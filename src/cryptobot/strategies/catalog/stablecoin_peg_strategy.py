"""Stablecoin peg band.

`entry` used to be dead: `signal()` hard-coded the 0.5% band and never read the
config field (15/15 perturbations identical).

`entry` is now the **relative** deviation from the `period` mean at which the
strategy trades, i.e. `|close / sma - 1| > entry`. Its default is corrected to
`0.005` so that the out-of-the-box behaviour is unchanged; the old default of
`2.0` was inherited from the catalog's z-score-scored `entry` knobs and never
took effect.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.indicators import sma
from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class StablecoinPegConfig:
    period: int = 60
    #: entry band as a relative deviation from the period mean (0.005 = 50 bps)
    entry: float = 0.005
    quantity: Decimal = Decimal("1")


class StablecoinPegStrategy(SignalStrategy):
    name = "stablecoin_peg"

    def __init__(self, config: StablecoinPegConfig | None = None):
        super().__init__(config or StablecoinPegConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        m = sma(closes, self.config.period)
        if m != m or m == 0:
            return 0
        dev = (closes[-1] - m) / m
        if dev > self.config.entry:
            return -1
        if dev < -self.config.entry:
            return 1
        return 0
