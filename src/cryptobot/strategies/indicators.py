"""Shared streaming indicator helpers for signal strategies.

Pure numpy over rolling windows. Every function takes a plain list/array of
bars (closes, highs, lows, volumes) and returns either a scalar signal value
or a series; the streaming wrappers in `signal_base` handle windowing.
"""

from __future__ import annotations

from decimal import Decimal

import numpy as np


def sma(values, period: int) -> float:
    if len(values) < period:
        return float("nan")
    return float(np.mean(values[-period:]))


def ema(values, period: int) -> float:
    if len(values) < period:
        return float("nan")
    a = np.asarray(values, dtype=float)
    k = 2.0 / (period + 1)
    out = a[0]
    for x in a[1:]:
        out = k * x + (1 - k) * out
    return float(out)


def _ema_series(values, period: int) -> np.ndarray:
    """Full EMA series (prefix-stable recursion), one value per input bar."""
    a = np.asarray(values, dtype=float)
    k = 2.0 / (period + 1)
    out = np.empty(len(a), dtype=float)
    out[0] = a[0]
    for i in range(1, len(a)):
        out[i] = k * a[i] + (1 - k) * out[i - 1]
    return out


def dema(values, period: int) -> float:
    """Double exponential moving average: 2*EMA - EMA(EMA)."""
    if len(values) < period:
        return float("nan")
    e1 = _ema_series(values, period)
    e2 = _ema_series(e1, period)
    return float(2.0 * e1[-1] - e2[-1])


def tema(values, period: int) -> float:
    """Triple exponential moving average: 3*EMA1 - 3*EMA2 + EMA3."""
    if len(values) < period:
        return float("nan")
    e1 = _ema_series(values, period)
    e2 = _ema_series(e1, period)
    e3 = _ema_series(e2, period)
    return float(3.0 * e1[-1] - 3.0 * e2[-1] + e3[-1])


def _wma_last(values, period: int) -> float:
    """Last weighted-moving-average value (most recent bar weighted highest)."""
    if len(values) < period:
        return float("nan")
    a = np.asarray(values[-period:], dtype=float)
    w = np.arange(1, period + 1, dtype=float)
    return float(np.sum(a * w) / w.sum())


def hull(values, period: int) -> float:
    """Hull moving average: WMA(2*WMA(n/2) - WMA(n), sqrt(n))."""
    if len(values) < period:
        return float("nan")
    half = max(1, period // 2)
    sqrt_p = max(1, int(round(period ** 0.5)))
    raws: list[float] = []
    for back in range(sqrt_p - 1, -1, -1):
        sub = values if back == 0 else values[: len(values) - back]
        wf = _wma_last(sub, period)
        wh = _wma_last(sub, half)
        if wf != wf or wh != wh:
            return float("nan")
        raws.append(2.0 * wf - wh)
    w = np.arange(1, sqrt_p + 1, dtype=float)
    return float(np.sum(np.asarray(raws) * w) / w.sum())


def kama(values, period: int = 20, fast: int = 2, slow: int = 30) -> float:
    """Kaufman adaptive moving average (efficiency-ratio smoothed)."""
    a = np.asarray(values, dtype=float)
    n = len(a)
    if n < period + 1:
        return float("nan")
    fast_sc = 2.0 / (fast + 1)
    slow_sc = 2.0 / (slow + 1)
    vol = float(sum(abs(a[j] - a[j - 1]) for j in range(1, period + 1)))
    kama_prev = float(a[period])
    for i in range(period + 1, n):
        vol = vol - abs(a[i - period] - a[i - period - 1]) + abs(a[i] - a[i - 1])
        change = abs(a[i] - a[i - period])
        er = 0.0 if vol == 0 else change / vol
        sc = (er * (fast_sc - slow_sc) + slow_sc) ** 2
        kama_prev = kama_prev + sc * (a[i] - kama_prev)
    return float(kama_prev)


def rsi(closes, period: int = 14) -> float:
    if len(closes) < period + 1:
        return float("nan")
    a = np.asarray(closes, dtype=float)
    d = np.diff(a[-(period + 1) :])
    gains = d[d > 0].sum() / period
    losses = -d[d < 0].sum() / period
    if losses == 0:
        return 100.0
    rs = gains / losses
    return float(100 - 100 / (1 + rs))


def stochastic(closes, highs, lows, period: int = 14) -> float:
    if len(closes) < period:
        return float("nan")
    hh = max(highs[-period:])
    ll = min(lows[-period:])
    if hh == ll:
        return 50.0
    return float((closes[-1] - ll) / (hh - ll) * 100)


def macd(closes, fast: int = 12, slow: int = 26) -> float:
    if len(closes) < slow:
        return float("nan")
    return float(ema(closes, fast) - ema(closes, slow))


def macd_signal(closes, fast: int = 12, slow: int = 26, sig: int = 9) -> float:
    if len(closes) < slow + sig:
        return float("nan")
    # One-pass equivalent of the original
    #   line = [macd(closes[: i + 1], fast, slow) for i in range(slow, len(closes))]
    #   return mean(line[-sig:])
    # The EMA recursion is prefix-stable (ema(prefix_i) = k*x + (1-k)*ema(prefix_{i-1})),
    # so carrying the running EMAs forward produces bit-identical line values
    # without re-walking the whole history per bar (was O(n^2): 260s per
    # 7200-bar backtest, now sub-second).
    kf = 2.0 / (fast + 1)
    ks = 2.0 / (slow + 1)
    a = np.asarray(closes, dtype=float)
    ef = es = float(a[0])
    line: list[float] = []
    for i, x in enumerate(a):
        if i > 0:
            xf = float(x)
            ef = kf * xf + (1 - kf) * ef
            es = ks * xf + (1 - ks) * es
        if i >= slow:
            line.append(ef - es)
    return float(np.mean(line[-sig:]))


def atr(highs, lows, closes, period: int = 14) -> float:
    if len(closes) < period + 1:
        return float("nan")
    trs = []
    for i in range(len(closes) - period, len(closes)):
        hi0, lo0, pc = highs[i], lows[i], closes[i - 1]
        trs.append(max(hi0 - lo0, abs(hi0 - pc), abs(lo0 - pc)))
    return float(np.mean(trs))


def true_range(high, low, prev_close) -> float:
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def cci(highs, lows, closes, period: int = 20) -> float:
    if len(closes) < period:
        return float("nan")
    tp = [(highs[i] + lows[i] + closes[i]) / 3 for i in range(-period, 0)]
    mean = float(np.mean(tp))
    md = float(np.mean([abs(t - mean) for t in tp]))
    if md == 0:
        return 0.0
    return float((tp[-1] - mean) / (0.015 * md))


def williams_r(closes, highs, lows, period: int = 14) -> float:
    if len(closes) < period:
        return float("nan")
    hh = max(highs[-period:])
    ll = min(lows[-period:])
    if hh == ll:
        return -50.0
    return float((hh - closes[-1]) / (hh - ll) * -100)


def roc(closes, period: int) -> float:
    if len(closes) <= period:
        return float("nan")
    prev = closes[-period - 1]
    if prev == 0:
        return 0.0
    return float((closes[-1] - prev) / prev)


def zscore(values) -> float:
    a = np.asarray(values, dtype=float)
    if len(a) < 2:
        return float("nan")
    sd = a.std()
    if sd == 0:
        return 0.0
    return float((a[-1] - a.mean()) / sd)


def bollinger_position(closes, period: int = 20, n_std: float = 2.0) -> float:
    """-1..1: where close sits between lower and upper band."""
    if len(closes) < period:
        return float("nan")
    a = np.asarray(closes[-period:], dtype=float)
    mid = float(a.mean())
    sd = float(a.std())
    if sd == 0:
        return 0.0
    return float((a[-1] - mid) / (n_std * sd))


def obv(closes, volumes) -> float:
    if len(closes) < 2 or len(volumes) < len(closes):
        return float("nan")
    v = 0.0
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            v += volumes[i]
        elif closes[i] < closes[i - 1]:
            v -= volumes[i]
    return float(v)


def mfi(closes, highs, lows, volumes, period: int = 14) -> float:
    if len(closes) < period + 1:
        return float("nan")
    pos = neg = 0.0
    for i in range(-period, 0):
        tp = (highs[i] + lows[i] + closes[i]) / 3
        prev_tp = (highs[i - 1] + lows[i - 1] + closes[i - 1]) / 3
        flow = tp * volumes[i]
        if tp > prev_tp:
            pos += flow
        elif tp < prev_tp:
            neg += flow
    if neg == 0:
        return 100.0
    return float(100 - 100 / (1 + pos / neg))


def donchian_high(highs, period: int) -> float:
    if len(highs) < period:
        return float("nan")
    return float(max(highs[-period:]))


def donchian_low(lows, period: int) -> float:
    if len(lows) < period:
        return float("nan")
    return float(min(lows[-period:]))


def make_order(symbol: str, side, quantity: Decimal, strategy: str, order_type=None):
    from cryptobot.core.events import OrderEvent, OrderType

    return OrderEvent(
        symbol=symbol,
        side=side,
        type=order_type or OrderType.MARKET,
        quantity=quantity,
        strategy=strategy,
    )


__all__ = [
    "atr",
    "bollinger_position",
    "cci",
    "chaikin_mf",
    "cumulative_delta",
    "donchian_high",
    "donchian_low",
    "ema",
    "dema",
    "tema",
    "hull",
    "kama",
    "fisher_transform",
    "keltner_mid",
    "inside_bar",
    "macd",
    "macd_signal",
    "make_order",
    "mfi",
    "obv",
    "range_n",
    "roc",
    "rsi",
    "sma",
    "stochastic",
    "true_range",
    "vwap",
    "williams_r",
    "zscore",
]


def vwap(closes, volumes) -> float:
    """Session VWAP over the buffer (cumulative tp*vol / vol)."""
    if not closes or not volumes or sum(volumes) == 0:
        return float("nan")
    tp = sum(c * v for c, v in zip(closes, volumes, strict=False))
    return float(tp / sum(volumes))


def keltner_mid(closes, period: int = 20) -> float:
    """Keltner middle line: EMA of closes."""
    return float(ema(closes, period))


def fisher_transform(closes, period: int = 10) -> float:
    """Fisher transform of normalized price within period range."""
    import numpy as _np

    if len(closes) < period:
        return float("nan")
    a = closes[-period:]
    hi, lo = max(a), min(a)
    if hi == lo:
        return 0.0
    norm = 2.0 * ((a[-1] - lo) / (hi - lo) - 0.5)
    norm = max(-0.999, min(0.999, norm))
    return float(0.5 * _np.log((1 + norm) / (1 - norm)))


def range_n(highs, lows, n: int) -> float:
    """True-range size of the nth most recent bar (n=1 = current)."""
    i = -n
    if len(highs) < n or len(lows) < n:
        return float("nan")
    return float(highs[i] - lows[i])


def inside_bar(highs, lows) -> bool:
    """True if current bar is contained within the previous bar's range."""
    if len(highs) < 2:
        return False
    return highs[-1] <= highs[-2] and lows[-1] >= lows[-2]


def chaikin_mf(closes, highs, lows, volumes, period: int = 20) -> float:
    """Chaikin Money Flow: sum(MFV) / sum(volume) over window."""
    if len(closes) < period:
        return float("nan")
    mfv_total = 0.0
    vol_total = 0.0
    for i in range(-period, 0):
        hi, lo, c = highs[i], lows[i], closes[i]
        if hi == lo:
            continue
        mfm = ((c - lo) - (hi - c)) / (hi - lo)
        mfv_total += mfm * volumes[i]
        vol_total += volumes[i]
    if vol_total <= 0:
        return float("nan")
    return float(mfv_total / vol_total)


def cumulative_delta(closes, volumes, window: int = 30) -> float:
    """Buy/sell pressure proxy: sum of |close-open-signed| * volume."""
    if len(closes) < window + 1:
        return float("nan")
    delta = 0.0
    for i in range(-window, 0):
        if closes[i] > closes[i - 1]:
            delta += volumes[i]
        elif closes[i] < closes[i - 1]:
            delta -= volumes[i]
    return float(delta)
