"""ADX/DI trend strategy.

Signal: follow the dominant directional indicator, but only when trend strength
justifies it (Wilder's ADX above ``threshold``).

Wilder (1978) computation, implemented here rather than in
``strategies.indicators`` because ADX needs Wilder's RMA smoothing, which no
shared helper provides:

    TR_t  = max(H_t - L_t, |H_t - C_{t-1}|, |L_t - C_{t-1}|)
    +DM_t = (H_t - H_{t-1}) if it dominates (L_{t-1} - L_t) and > 0 else 0
    -DM_t = (L_{t-1} - L_t) if it dominates (H_t - H_{t-1}) and > 0 else 0

TR/+DM/-DM are smoothed with Wilder's RMA (seed = simple average of the first
``period`` values, then ``prev - prev/period + current``), giving

    +DI = 100 * RMA(+DM) / RMA(TR)          -DI = 100 * RMA(-DM) / RMA(TR)
    DX  = 100 * |+DI - -DI| / (+DI + -DI)
    ADX = RMA(DX)

``config.period`` drives every smoothing window, so it is live: a longer period
smooths more and yields a different ADX/DI series.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.strategies.signal_base import SignalStrategy


@dataclass
class AdxTrendConfig:
    period: int = 14
    threshold: float = 25.0
    quantity: Decimal = Decimal("1")


def _rma(values: list[float], period: int) -> list[float]:
    """Wilder's smoothing. Returns a series aligned to ``values``, NaN-padded.

    Seed is the simple average of the first ``period`` values; thereafter
    ``prev - prev / period + current`` (the standard RMA recursion).
    """
    out = [float("nan")] * len(values)
    if len(values) < period:
        return out
    smoothed = sum(values[:period]) / period
    out[period - 1] = smoothed
    for i in range(period, len(values)):
        smoothed = smoothed - smoothed / period + values[i]
        out[i] = smoothed
    return out


def _directional_movement(
    highs: list[float], lows: list[float]
) -> tuple[list[float], list[float]]:
    """+DM and -DM series indexed to match ``highs``; index 0 is NaN (no prior bar)."""
    plus = [float("nan")] * len(highs)
    minus = [float("nan")] * len(highs)
    for i in range(1, len(highs)):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus[i] = up if (up > down and up > 0) else 0.0
        minus[i] = down if (down > up and down > 0) else 0.0
    return plus, minus


def wilder_di(
    highs: list[float], lows: list[float], closes: list[float], period: int
) -> tuple[float, float]:
    """Latest (+DI, -DI) as percentages. (NaN, NaN) when not yet defined."""
    n = len(closes)
    if n < period + 1:
        return float("nan"), float("nan")

    tr = [float("nan")] * n
    for i in range(1, n):
        prev_close = closes[i - 1]
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - prev_close),
            abs(lows[i] - prev_close),
        )
    plus_dm, minus_dm = _directional_movement(highs, lows)

    tr_s = _rma(tr[1:], period)
    plus_s = _rma(plus_dm[1:], period)
    minus_s = _rma(minus_dm[1:], period)

    if tr_s[-1] != tr_s[-1] or tr_s[-1] == 0:
        return float("nan"), float("nan")
    return (
        100.0 * plus_s[-1] / tr_s[-1],
        100.0 * minus_s[-1] / tr_s[-1],
    )


def wilder_adx(
    highs: list[float], lows: list[float], closes: list[float], period: int
) -> float:
    """Latest Wilder ADX in [0, 100]. NaN until ``2 * period - 1`` bars are available."""
    n = len(closes)
    if n < 2 * period:
        return float("nan")

    tr = [float("nan")] * n
    for i in range(1, n):
        prev_close = closes[i - 1]
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - prev_close),
            abs(lows[i] - prev_close),
        )
    plus_dm, minus_dm = _directional_movement(highs, lows)

    tr_s = _rma(tr[1:], period)
    plus_s = _rma(plus_dm[1:], period)
    minus_s = _rma(minus_dm[1:], period)

    # DX is defined once the smoothed TR/DM are, i.e. from RMA index period - 1.
    dx: list[float] = []
    for i in range(len(tr_s)):
        if tr_s[i] != tr_s[i] or tr_s[i] == 0:
            dx.append(float("nan"))
            continue
        p = 100.0 * plus_s[i] / tr_s[i]
        m = 100.0 * minus_s[i] / tr_s[i]
        total = p + m
        dx.append(100.0 * abs(p - m) / total if total > 0 else 0.0)

    first_dx = period - 1
    if first_dx + period > len(dx):
        return float("nan")
    seed = [dx[i] for i in range(first_dx, first_dx + period)]
    if any(d != d for d in seed):
        return float("nan")

    adx = sum(seed) / period
    for i in range(first_dx + period, len(dx)):
        if dx[i] != dx[i]:
            continue
        adx = (adx * (period - 1) + dx[i]) / period
    return adx


class AdxTrendStrategy(SignalStrategy):
    """+1 when +DI leads and ADX clears the threshold, -1 for the mirror case."""

    name = "adx_trend"

    def __init__(self, config: AdxTrendConfig | None = None):
        super().__init__(config or AdxTrendConfig())

    def warmup(self, closes) -> int:
        # Wilder's ADX needs period bars to seed the RMA of TR/DM, then period
        # bars of DX to seed the ADX itself.
        return 2 * self.config.period

    def signal(self, closes, highs, lows, volumes):
        period = self.config.period
        if len(closes) < 2 * period:
            return 0
        adx = wilder_adx(highs, lows, closes, period)
        plus_di, minus_di = wilder_di(highs, lows, closes, period)
        if adx != adx or plus_di != plus_di or minus_di != minus_di:
            return 0
        if adx < self.config.threshold:
            return 0
        if plus_di > minus_di:
            return 1
        if minus_di > plus_di:
            return -1
        return 0
