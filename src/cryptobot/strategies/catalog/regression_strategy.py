"""Linear regression.

This module was named "Linear regression" and contained none: it was
`sma(closes, period)` plus a level comparison — a buy-high rule (forward
returns of flagged vs unflagged cells were negative at t = -10.7 / -11.5 / -18.8
for SMA20/50/200).

Semantics now (both legs come from a single OLS fit):

* regress `close` on the bar index `0 .. period-1` over the trailing `period`
  bars;
* `slope` — the fitted per-bar slope (zero for a flat window);
* `level`  — the fitted line's value at the centre of the window, i.e. the
  mean of the OLS fit, which equals the window mean because the regressor is
  mean-zero by construction;
* **long** when the fitted slope is positive *and* the close sits above that
  fitted level; **short** when the slope is negative *and* the close sits below
  it; flat otherwise.

The slope term is the part the old rule lacked entirely — the level comparison
alone is the buy-high rule that was proven backwards.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class RegressionConfig:
    period: int = 20
    quantity: Decimal = Decimal("1")


def _ols_on_time(values, period: int) -> tuple[float, float]:
    """OLS of ``values`` on the bar index. Returns ``(slope, fitted_level)``."""
    if period < 2:
        return float("nan"), float("nan")
    w = values[-period:]
    n = len(w)
    if n < 2:
        return float("nan"), float("nan")
    xbar = (n - 1) / 2.0
    level = sum(w) / n
    sxy = 0.0
    sxx = 0.0
    for i, y in enumerate(w):
        dx = i - xbar
        sxy += dx * (y - level)
        sxx += dx * dx
    if sxx == 0:
        return float("nan"), float("nan")
    return sxy / sxx, level


class RegressionStrategy(SignalStrategy):
    name = "regression"

    def __init__(self, config: RegressionConfig | None = None):
        super().__init__(config or RegressionConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        slope, level = _ols_on_time(closes, self.config.period)
        if slope != slope:
            return 0
        if slope > 0 and closes[-1] > level:
            return 1
        if slope < 0 and closes[-1] < level:
            return -1
        return 0
