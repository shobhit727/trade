from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cryptobot.backtest.runner import OhlcvBar


@dataclass
class FeatureConfig:
    rsi_period: int = 14
    ema_fast: int = 12
    ema_slow: int = 26
    atr_period: int = 14
    macd_signal: int = 9
    bb_period: int = 20
    bb_std: float = 2.0


def _to_array(bars: list[OhlcvBar], key: str):
    fn = getattr(bars[0], key)
    return np.asarray([float(fn(b)) for b in bars], dtype=float) if False else np.asarray(
        [float(getattr(b, key)) for b in bars], dtype=float
    )


def _rsi(close: np.ndarray, period: int) -> np.ndarray:
    n = close.size
    out = np.full(n, 50.0)
    if n < period + 1:
        return out
    diff = np.diff(close)
    gains = np.clip(diff, 0, None)
    losses = np.clip(-diff, 0, None)
    avg_g = np.zeros(n)
    avg_l = np.zeros(n)
    avg_g[period] = gains[:period].mean()
    avg_l[period] = losses[:period].mean()
    for i in range(period + 1, n):
        avg_g[i] = (avg_g[i - 1] * (period - 1) + gains[i - 1]) / period
        avg_l[i] = (avg_l[i - 1] * (period - 1) + losses[i - 1]) / period
    rs = np.divide(avg_g, np.where(avg_l == 0, 1e-12, avg_l))
    out = 100 - 100 / (1 + rs)
    return out


def _ema(series: np.ndarray, period: int) -> np.ndarray:
    n = series.size
    out = np.zeros(n)
    if n == 0:
        return out
    k = 2.0 / (period + 1)
    out[0] = series[0]
    for i in range(1, n):
        out[i] = series[i] * k + out[i - 1] * (1 - k)
    return out


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    n = close.size
    out = np.full(n, np.nan)
    if n < 2:
        return out
    prev_close = close[:-1]
    tr = np.maximum(high[1:] - low[1:], np.maximum(np.abs(high[1:] - prev_close), np.abs(low[1:] - prev_close)))
    out[1:] = tr
    if n >= period:
        for i in range(period, n):
            out[i] = (out[i - 1] * (period - 1) + tr[i - 1]) / period
    return out


def _macd(close: np.ndarray, fast: int, slow: int, signal: int):
    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)
    macd_line = ema_fast - ema_slow
    return macd_line, _ema(macd_line, signal)


def _bbands(close: np.ndarray, period: int, k: float):
    n = close.size
    mid = np.full(n, np.nan)
    upper = np.full(n, np.nan)
    lower = np.full(n, np.nan)
    for i in range(period - 1, n):
        window = close[i - period + 1 : i + 1]
        mu = window.mean()
        sd = window.std(ddof=0)
        mid[i] = mu
        upper[i] = mu + k * sd
        lower[i] = mu - k * sd
    return mid, upper, lower


def build_features(bars: list[OhlcvBar], config: FeatureConfig | None = None) -> np.ndarray:
    cfg = config or FeatureConfig()
    if not bars:
        return np.zeros((0, 8), dtype=float)
    opens = _to_array(bars, "open")
    highs = _to_array(bars, "high")
    lows = _to_array(bars, "low")
    closes = _to_array(bars, "close")
    volumes = _to_array(bars, "volume")
    n = closes.size
    rsi = _rsi(closes, cfg.rsi_period)
    macd_line, macd_signal = _macd(closes, cfg.ema_fast, cfg.ema_slow, cfg.macd_signal)
    atr = _atr(highs, lows, closes, cfg.atr_period)
    bb_mid, bb_upper, bb_lower = _bbands(closes, cfg.bb_period, cfg.bb_std)
    returns = np.zeros(n)
    if n > 1:
        returns[1:] = (closes[1:] - closes[:-1]) / closes[:-1]

    sma_ratio = np.where(bb_mid > 0, closes / bb_mid, 1.0)
    bb_width = np.where(bb_mid > 0, (bb_upper - bb_lower) / bb_mid, 0.0)
    log_volume = np.log1p(np.where(volumes > 0, volumes, 1.0))

    features = np.column_stack([
        returns,
        rsi / 100.0,
        macd_line,
        macd_signal,
        np.where(np.isnan(atr), 0.0, atr) / closes,
        sma_ratio,
        bb_width,
        log_volume,
    ])
    rows = []
    for i in range(closes.size):
        if np.isnan(features[i]).any():
            continue
        rows.append(features[i])
    return np.asarray(rows, dtype=float)


def future_returns(bars: list[OhlcvBar], horizon: int = 5) -> np.ndarray:
    n = len(bars)
    out = np.zeros(n - horizon)
    closes = np.asarray([float(b.close) for b in bars], dtype=float)
    for i in range(n - horizon):
        prev = closes[i]
        nxt = closes[i + horizon]
        if prev > 0:
            out[i] = (nxt - prev) / prev
    return out


__all__ = [
    "FeatureConfig",
    "build_features",
    "future_returns",
]
