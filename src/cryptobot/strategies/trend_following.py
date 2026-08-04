from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal

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


@dataclass
class _TrendState:
    """Per-symbol streaming indicator state (O(1) per bar, Wilder-style)."""

    bars: int = 0
    ema_fast: float = 0.0
    ema_slow: float = 0.0
    ema_fast_seeded: bool = False
    ema_slow_seeded: bool = False
    prev_high: float = 0.0
    prev_low: float = 0.0
    prev_close: float = 0.0
    tr_sum: float = 0.0
    plus_sum: float = 0.0
    minus_sum: float = 0.0
    tr_window: deque[float] = field(default_factory=lambda: deque())
    plus_window: deque[float] = field(default_factory=lambda: deque())
    minus_window: deque[float] = field(default_factory=lambda: deque())
    dx_sum: float = 0.0
    dx_window: deque[float] = field(default_factory=lambda: deque())
    atr: float = 0.0
    adx: float = 0.0


class TrendFollowingStrategy:
    name = "trend_following"

    def __init__(self, config: TrendFollowingConfig | None = None):
        self.config = config or TrendFollowingConfig()
        self._state: dict[str, _TrendState] = {}
        self._entry_stop: dict[str, float] = {}
        cfg = self.config
        self._k_fast = 2.0 / (cfg.fast + 1)
        self._k_slow = 2.0 / (cfg.slow + 1)
        self._slow = cfg.slow
        self._atr_p = cfg.atr_period
        self._adx_p = cfg.adx_period
        self._adx_gate = 2 * cfg.adx_period + 1
        self._adx_thr = cfg.adx_threshold
        self._atr_mult = cfg.atr_multiplier
        self._qty = cfg.quantity

    def _st(self, symbol: str) -> _TrendState:
        return self._state.setdefault(symbol, _TrendState())

    def _update_indicators(self, st: _TrendState, high: float, low: float, close: float) -> None:
        bars = st.bars + 1
        st.bars = bars

        if st.ema_fast_seeded:
            kf = self._k_fast
            st.ema_fast = close * kf + st.ema_fast * (1 - kf)
        else:
            st.ema_fast = close
            st.ema_fast_seeded = True

        if st.ema_slow_seeded:
            ks = self._k_slow
            st.ema_slow = close * ks + st.ema_slow * (1 - ks)
        else:
            st.ema_slow = close
            st.ema_slow_seeded = True

        if bars == 1:
            st.prev_high, st.prev_low, st.prev_close = high, low, close
            return

        ph, pl, pc = st.prev_high, st.prev_low, st.prev_close
        up_move = high - ph
        down_move = pl - low
        plus_dm = up_move if (up_move > down_move and up_move > 0) else 0.0
        minus_dm = down_move if (down_move > up_move and down_move > 0) else 0.0
        d1 = high - low
        d2 = high - pc
        d3 = low - pc
        tr = d1 if d1 > d2 else d2
        if d3 > tr:
            tr = d3

        atr_p = self._atr_p
        adx_p = self._adx_p
        tr_w = st.tr_window
        plus_w = st.plus_window
        minus_w = st.minus_window
        tr_w.append(tr)
        plus_w.append(plus_dm)
        minus_w.append(minus_dm)
        if len(tr_w) > atr_p:
            st.tr_sum += tr - tr_w.popleft()
        else:
            st.tr_sum += tr
        if len(plus_w) > adx_p:
            st.plus_sum += plus_dm - plus_w.popleft()
        else:
            st.plus_sum += plus_dm
        if len(minus_w) > adx_p:
            st.minus_sum += minus_dm - minus_w.popleft()
        else:
            st.minus_sum += minus_dm

        if len(tr_w) == atr_p:
            st.atr = st.tr_sum / atr_p

        st.prev_high, st.prev_low, st.prev_close = high, low, close

        if len(plus_w) == adx_p and bars >= self._adx_gate:
            s_tr = st.tr_sum
            s_plus = st.plus_sum
            s_minus = st.minus_sum
            pdi = 100.0 * s_plus / s_tr if s_tr > 0 else 0.0
            mdi = 100.0 * s_minus / s_tr if s_tr > 0 else 0.0
            dx = 100.0 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) > 0 else 0.0
            dx_w = st.dx_window
            dx_w.append(dx)
            st.dx_sum += dx
            if len(dx_w) > adx_p:
                st.dx_sum -= dx_w.popleft()
            if len(dx_w) == adx_p:
                st.adx = st.dx_sum / adx_p

    def feed(self, symbol: str, high: float, low: float, close: float) -> OrderEvent | None:
        st = self._state.get(symbol)
        if st is None:
            st = _TrendState()
            self._state[symbol] = st
        self._update_indicators(st, high, low, close)
        if st.bars < self._slow:
            return None
        entry_stop = self._entry_stop
        if st.ema_fast > st.ema_slow and st.adx > self._adx_thr and symbol not in entry_stop:
            entry_stop[symbol] = close - self._atr_mult * st.atr
            return OrderEvent(symbol=symbol, side=OrderSide.BUY, quantity=self._qty, price=Decimal(str(round(close, 8))))
        if st.ema_fast < st.ema_slow and symbol in entry_stop:
            entry_stop.pop(symbol, None)
            return OrderEvent(symbol=symbol, side=OrderSide.SELL, quantity=self._qty, price=Decimal(str(round(close, 8))))
        if symbol in entry_stop and close <= entry_stop[symbol]:
            entry_stop.pop(symbol, None)
            return OrderEvent(symbol=symbol, side=OrderSide.SELL, quantity=self._qty, price=Decimal(str(round(close, 8))))
        return None
