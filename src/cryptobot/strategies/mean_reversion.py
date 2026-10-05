from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from decimal import Decimal

import numpy as np

from cryptobot.core.events import OrderEvent, OrderSide, OrderType


@dataclass
class MeanReversionConfig:
    lookback: int = 20
    z_entry: float = 2.0
    z_exit: float = 0.5
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    bb_period: int = 20
    bb_std: float = 2.0
    quantity: Decimal = Decimal("1")
    # Trend filter: only take longs above the SMA, shorts below it. Prevents
    # buying the bottom of a waterfall; 0 disables the filter.
    trend_period: int = 0
    # Hard exit discipline: take-profit / stop-loss as fractional moves from
    # entry price, and a hard bar-count cap. 0 disables that specific guard.
    take_profit: float = 0.02
    stop_loss: float = 0.02
    max_hold_bars: int = 48


@dataclass
class _PositionState:
    side: str  # "long" or "short"
    entry_price: float
    quantity: Decimal
    bars_held: int = 0


class MeanReversionStrategy:
    name = "mean_reversion"

    def __init__(self, config: MeanReversionConfig | None = None):
        self.config = config or MeanReversionConfig()
        self._prices: dict[str, deque[float]] = {}
        self._positions: dict[str, _PositionState] = {}

    def _exit_order(self, symbol: str, pos: _PositionState, price: float, z: float) -> OrderEvent | None:
        """Emit a full-position market exit if any exit rule fires."""
        if pos.side == "long":
            pnl_pct = (price - pos.entry_price) / pos.entry_price
            exit_side = OrderSide.SELL
        else:
            pnl_pct = (pos.entry_price - price) / pos.entry_price
            exit_side = OrderSide.BUY
        tp = self.config.take_profit
        sl = self.config.stop_loss
        max_hold = self.config.max_hold_bars
        if (
            abs(z) <= self.config.z_exit
            or (tp > 0 and pnl_pct >= tp)
            or (sl > 0 and pnl_pct <= -sl)
            or (max_hold > 0 and pos.bars_held >= max_hold)
        ):
            return OrderEvent(
                symbol=symbol,
                side=exit_side,
                type=OrderType.MARKET,
                quantity=pos.quantity,
                price=Decimal("0"),
                reduce_only=True,
            )
        return None

    def feed(self, symbol: str, price: float) -> OrderEvent | None:
        lookback = self.config.lookback
        bb_period = self.config.bb_period
        rsi_period = self.config.rsi_period
        trend_period = self.config.trend_period
        buf = self._prices.setdefault(
            symbol,
            deque(maxlen=max(lookback, bb_period, rsi_period + 1, trend_period)),
        )
        buf.append(price)
        if len(buf) < max(bb_period, trend_period if trend_period else 0):
            return None
        arr = np.fromiter(buf, dtype=float)
        bb_mid = arr[-bb_period:].mean()
        bb_std = arr[-bb_period:].std(ddof=0)
        bb_upper = bb_mid + self.config.bb_std * bb_std
        bb_lower = bb_mid - self.config.bb_std * bb_std

        look = arr[-lookback:]
        mean = look.mean()
        std = look.std(ddof=0)
        if std <= 0:
            return None
        z = (price - mean) / std

        gains = np.clip(np.diff(arr[-rsi_period - 1:]), 0, None).mean()
        losses = (-np.clip(np.diff(arr[-rsi_period - 1:]), None, 0)).mean()
        if losses == 0:
            rsi = 100.0
        else:
            rs = gains / losses
            with np.errstate(divide="ignore", invalid="ignore"):
                rsi = 100 - 100 / (1 + rs)

        trend_ok = None
        if trend_period > 0:
            trend_ok = price > arr[-trend_period:].mean()

        pos = self._positions.get(symbol)
        if pos is not None:
            pos.bars_held += 1
            exit_order = self._exit_order(symbol, pos, price, z)
            if exit_order is not None:
                del self._positions[symbol]
                return exit_order
            return None

        if (
            z <= -self.config.z_entry
            and rsi <= self.config.rsi_oversold
            and price <= bb_lower
            and (trend_ok is None or trend_ok)
        ):
            self._positions[symbol] = _PositionState(side="long", entry_price=price, quantity=self.config.quantity)
            stop_price = price * (1 - self.config.stop_loss) if self.config.stop_loss > 0 else None
            return OrderEvent(
                symbol=symbol,
                side=OrderSide.BUY,
                quantity=self.config.quantity,
                price=Decimal(str(round(price, 8))),
                stop_price=Decimal(str(round(stop_price, 8))) if stop_price is not None else None,
            )
        if (
            z >= self.config.z_entry
            and rsi >= self.config.rsi_overbought
            and price >= bb_upper
            and (trend_ok is None or not trend_ok)
        ):
            self._positions[symbol] = _PositionState(side="short", entry_price=price, quantity=self.config.quantity)
            stop_price = price * (1 + self.config.stop_loss) if self.config.stop_loss > 0 else None
            return OrderEvent(
                symbol=symbol,
                side=OrderSide.SELL,
                quantity=self.config.quantity,
                price=Decimal(str(round(price, 8))),
                stop_price=Decimal(str(round(stop_price, 8))) if stop_price is not None else None,
            )
        return None
