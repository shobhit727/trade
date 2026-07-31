from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from decimal import Decimal

import numpy as np

from cryptobot.core.events import OrderEvent, OrderSide


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


class MeanReversionStrategy:
    name = "mean_reversion"

    def __init__(self, config: MeanReversionConfig | None = None):
        self.config = config or MeanReversionConfig()
        self._prices: dict[str, deque[float]] = {}

    def feed(self, symbol: str, price: float) -> OrderEvent | None:
        buf = self._prices.setdefault(symbol, deque(maxlen=max(self.config.lookback, self.config.bb_period, self.config.rsi_period + 1)))
        buf.append(price)
        if len(buf) < self.config.bb_period:
            return None
        arr = np.fromiter(buf, dtype=float)
        bb_mid = arr[-self.config.bb_period:].mean()
        bb_std = arr[-self.config.bb_period:].std(ddof=0)
        bb_upper = bb_mid + self.config.bb_std * bb_std
        bb_lower = bb_mid - self.config.bb_std * bb_std
        look = arr[-self.config.lookback:]
        mean = look.mean()
        std = look.std(ddof=0)
        if std <= 0:
            return None
        z = (price - mean) / std
        gains = np.clip(np.diff(arr[-self.config.rsi_period - 1:]), 0, None).mean()
        losses = np.clip(-np.diff(arr[-self.config.rsi_period - 1:]), None, 0).mean()
        if losses == 0:
            rsi = 100.0
        else:
            rs = gains / losses
            rsi = 100 - 100 / (1 + rs)

        if z <= -self.config.z_entry and rsi <= self.config.rsi_oversold and price <= bb_lower:
            return OrderEvent(symbol=symbol, side=OrderSide.BUY, quantity=self.config.quantity, price=Decimal(str(round(price, 8))))
        if z >= self.config.z_entry and rsi >= self.config.rsi_overbought and price >= bb_upper:
            return OrderEvent(symbol=symbol, side=OrderSide.SELL, quantity=self.config.quantity, price=Decimal(str(round(price, 8))))
        if abs(z) <= self.config.z_exit:
            return OrderEvent(symbol=symbol, side=OrderSide.BUY if z < 0 else OrderSide.SELL, quantity=self.config.quantity, price=Decimal("0"))
        return None
