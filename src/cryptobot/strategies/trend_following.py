from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from decimal import Decimal

import numpy as np

from cryptobot.core.events import OrderEvent, OrderSide


@dataclass
class TrendFollowingConfig:
    fast: int = 12
    slow: int = 26
    adx_period: int = 14
    adx_threshold: float = 20.0
    atr_period: int = 14
    atr_multiplier: float = 2.0
    quantity: Decimal = Decimal("1")


class TrendFollowingStrategy:
    name = "trend_following"

    def __init__(self, config: TrendFollowingConfig | None = None):
        self.config = config or TrendFollowingConfig()
        self._highs: dict[str, deque[float]] = {}
        self._lows: dict[str, deque[float]] = {}
        self._closes: dict[str, deque[float]] = {}
        self._entry_stop: dict[str, float] = {}

    def _buf(self, symbol: str) -> tuple[deque[float], deque[float], deque[float]]:
        n = max(self.config.slow, self.config.adx_period * 2 + 1, self.config.atr_period + 1)
        h = self._highs.setdefault(symbol, deque(maxlen=n))
        l = self._lows.setdefault(symbol, deque(maxlen=n))
        c = self._closes.setdefault(symbol, deque(maxlen=n))
        return h, l, c

    def feed(self, symbol: str, high: float, low: float, close: float) -> OrderEvent | None:
        h, l, c = self._buf(symbol)
        h.append(high)
        l.append(low)
        c.append(close)
        if len(c) < self.config.slow:
            return None
        closes = np.fromiter(c, dtype=float)
        ema_fast = self._ema(closes, self.config.fast)
        ema_slow = self._ema(closes, self.config.slow)
        adx = self._adx(np.fromiter(h, dtype=float), np.fromiter(l, dtype=float), closes, self.config.adx_period)
        atr = self._atr(np.fromiter(h, dtype=float), np.fromiter(l, dtype=float), closes, self.config.atr_period)
        if ema_fast > ema_slow and adx > self.config.adx_threshold and symbol not in self._entry_stop:
            self._entry_stop[symbol] = close - self.config.atr_multiplier * atr
            return OrderEvent(symbol=symbol, side=OrderSide.BUY, quantity=self.config.quantity, price=Decimal(str(round(close, 8))))
        if ema_fast < ema_slow and symbol in self._entry_stop:
            self._entry_stop.pop(symbol, None)
            return OrderEvent(symbol=symbol, side=OrderSide.SELL, quantity=self.config.quantity, price=Decimal(str(round(close, 8))))
        if symbol in self._entry_stop and close <= self._entry_stop[symbol]:
            self._entry_stop.pop(symbol, None)
            return OrderEvent(symbol=symbol, side=OrderSide.SELL, quantity=self.config.quantity, price=Decimal(str(round(close, 8))))
        return None

    @staticmethod
    def _ema(values: np.ndarray, period: int) -> float:
        if len(values) < period:
            return float(values.mean()) if len(values) else 0.0
        k = 2.0 / (period + 1)
        e = float(values[0])
        for v in values[1:]:
            e = float(v) * k + e * (1 - k)
        return e

    @staticmethod
    def _atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int) -> float:
        if len(closes) < 2:
            return 0.0
        tr = np.maximum(highs[1:] - lows[1:], np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1])))
        if len(tr) < period:
            return float(tr.mean()) if len(tr) else 0.0
        return float(tr[-period:].mean())

    @staticmethod
    def _adx(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int) -> float:
        if len(closes) < 2 * period + 1:
            return 0.0
        up_move = highs[1:] - highs[:-1]
        down_move = lows[:-1] - lows[1:]
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
        tr = np.maximum(highs[1:] - lows[1:], np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1])))
        atr = np.maximum.accumulate(tr) if len(tr) == 0 else tr
        if len(atr) < period:
            return 0.0
        atr_smooth = np.convolve(atr, np.ones(period) / period, mode="valid")
        plus_di = 100 * (np.convolve(plus_dm, np.ones(period) / period, mode="valid") / np.where(atr_smooth == 0, 1, atr_smooth))
        minus_di = 100 * (np.convolve(minus_dm, np.ones(period) / period, mode="valid") / np.where(atr_smooth == 0, 1, atr_smooth))
        dx = 100 * np.abs(plus_di - minus_di) / np.where(plus_di + minus_di == 0, 1, plus_di + minus_di)
        if len(dx) < period:
            return 0.0
        return float(dx[-period:].mean())
