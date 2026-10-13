"""Linear regression channel.

This module was named "Linear regression channel" and contained no regression
and no channel: it was ``sma(closes, period)`` plus ``close > sma ? 1 : -1`` —
the same buy-high rule already proven backwards in ``regression_strategy.py``.
On real NSE daily bars the forward 21-session return of flagged vs unflagged
cells is significantly NEGATIVE out of sample (t = -5.2 / -15.3 / -10.2 for
period 20 / 50 / 200), i.e. it bought names that had already run. It emitted
+/-1 on 99.6% of bars, so it never actually entered or exited anything, and it
had no channel-width knob at all — a "channel" strategy with a single line.

A channel is a fitted line plus bands around it, traded on channel breaks, so
that is what this now computes. All three pieces come from one OLS fit of
``close`` on the bar index ``0 .. period-1`` over the trailing ``period`` bars:

* ``slope``  — the fitted per-bar slope (zero for a flat window);
* ``level``  — the fitted line's value at the newest bar, i.e. the channel's
  centre line today (NOT the window mean, which is the line's mid-window value);
* ``sigma``  — the standard deviation of the residuals about that fitted line,
  which is what makes the band a *channel* rather than a line.

The channel half-width is ``multiplier * sigma``, so entry/exit condition on
the residual z-score against that band:

* **long** when the fitted slope is positive *and* the close breaks above the
  upper channel (``close > level + multiplier * sigma``, i.e. z > +1);
* **short** when the slope is negative *and* the close breaks below the lower
  channel (``close < level - multiplier * sigma``, i.e. z < -1);
* **flat** anywhere inside the channel — that is the exit.

The slope gate is the convention ``regression_strategy.py`` adopted: it is the
term the old rule lacked entirely, and it is what stops this channel from
degrading back into "buy whatever broke the top". The break is compared in
edge space rather than by dividing by ``multiplier * sigma``; that is the same
test whenever the band is positive, but stays defined when the residuals are
exactly zero (a perfectly linear window, where ``sigma == 0``).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class LinearRegChannelConfig:
    """``period`` sets the OLS lookback; ``multiplier`` sets the band width."""

    period: int = 20
    multiplier: float = 2.0
    quantity: Decimal = Decimal("1")


def _ols_on_time(values: Sequence[float], period: int) -> tuple[float, float]:
    """OLS of ``values`` on the bar index over the trailing ``period`` bars.

    Returns ``(slope, fitted_at_last_bar)``: the fitted per-bar slope and the
    fitted line's value at the newest bar. ``(nan, nan)`` when the window
    cannot support a fit (``period < 2`` or fewer than two bars available).
    """
    if period < 2:
        return float("nan"), float("nan")
    w = values[-period:]
    n = len(w)
    if n < 2:
        return float("nan"), float("nan")
    # The regressor is 0..n-1, so the window mean is the fitted value at the
    # window's midpoint xbar; the fitted value at the last bar (x = n-1) is the
    # window mean carried forward by slope * (n - 1 - xbar).
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
    slope = sxy / sxx
    return slope, level + slope * (n - 1 - xbar)


def _residual_sigma(values: Sequence[float], period: int, slope: float, level: float) -> float:
    """Std deviation of the residuals about the fitted line over the window.

    ``level`` is the fitted value at the last bar (see :func:`_ols_on_time`), so
    the fitted value at bar ``i`` is ``level + slope * (i - (n - 1))``.
    """
    w = values[-period:]
    n = len(w)
    if n < 2 or slope != slope:
        return float("nan")
    sse = 0.0
    for i, y in enumerate(w):
        sse += (y - (level + slope * (i - (n - 1)))) ** 2
    return math.sqrt(sse / n)


def _channel(
    values: Sequence[float], period: int, multiplier: float
) -> tuple[float, float, float]:
    """Fit the channel. Returns ``(slope, level, half_width)``.

    ``level`` is the fitted line at the newest bar; ``half_width`` is
    ``multiplier * residual sigma``. All three are ``nan`` when the window
    cannot support a fit.
    """
    slope, level = _ols_on_time(values, period)
    if slope != slope:
        return float("nan"), float("nan"), float("nan")
    sigma = _residual_sigma(values, period, slope, level)
    if sigma != sigma:
        return float("nan"), float("nan"), float("nan")
    return slope, level, float(multiplier) * sigma


class LinearRegChannelStrategy(SignalStrategy):
    name = "linear_reg_channel"

    def __init__(self, config: LinearRegChannelConfig | None = None):
        super().__init__(config or LinearRegChannelConfig())

    def warmup(self, closes) -> int:
        return self.config.period

    def signal(self, closes, highs, lows, volumes):
        slope, level, half = _channel(closes, self.config.period, self.config.multiplier)
        if slope != slope or half != half:
            return 0
        close = closes[-1]
        if slope > 0 and close > level + half:
            return 1
        if slope < 0 and close < level - half:
            return -1
        return 0
