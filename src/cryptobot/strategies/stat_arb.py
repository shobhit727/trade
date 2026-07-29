from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from decimal import Decimal
from typing import Deque, List, Optional, Tuple

from cryptobot.core.events import OrderEvent, OrderSide
from cryptobot.execution.engine import ExecutionEngine


@dataclass
class StatArbConfig:
    symbol_a: str = "BTCUSDT"
    symbol_b: str = "ETHUSDT"
    lookback: int = 60
    z_entry: float = 2.0
    z_exit: float = 0.4
    z_stop: float = 3.5
    quantity: Decimal = Decimal("0.1")
    fee_bps: float = 5.0
    min_correlation: float = 0.3
    half_life_bars: int = 24


class StatArbStrategy:
    name = "stat_arb"

    def __init__(self, config: Optional[StatArbConfig] = None):
        self.config = config or StatArbConfig()
        self._prices_a: Deque[float] = deque(maxlen=self.config.lookback)
        self._prices_b: Deque[float] = deque(maxlen=self.config.lookback)
        self._exec: Optional[ExecutionEngine] = None
        self.inventory_a = Decimal("0")
        self.inventory_b = Decimal("0")
        self.fills: List[OrderEvent] = []

    def attach_execution(self, engine: ExecutionEngine) -> None:
        self._exec = engine

    def feed(self, price_a: float, price_b: float) -> None:
        self._prices_a.append(price_a)
        self._prices_b.append(price_b)

    @staticmethod
    def _correlation(a: List[float], b: List[float]) -> float:
        n = min(len(a), len(b))
        if n < 5:
            return 0.0
        import numpy as np

        aa = np.asarray(a[-n:], dtype=float)
        bb = np.asarray(b[-n:], dtype=float)
        if aa.std() == 0 or bb.std() == 0:
            return 0.0
        return float(np.corrcoef(aa, bb)[0, 1])

    @staticmethod
    def _hedge_ratio(a: List[float], b: List[float]) -> float:
        import numpy as np

        n = min(len(a), len(b))
        if n < 5:
            return 1.0
        aa = np.asarray(a[-n:], dtype=float)
        bb = np.asarray(b[-n:], dtype=float)
        var_b = float(np.var(bb, ddof=0))
        if var_b <= 0:
            return 1.0
        cov = float(np.cov(aa, bb, ddof=0)[0, 1])
        return max(0.0, cov / var_b)

    @staticmethod
    def _zscore(series: List[float]) -> float:
        n = len(series)
        if n < 2:
            return 0.0
        import numpy as np

        arr = np.asarray(series, dtype=float)
        mu = float(arr.mean())
        sd = float(arr.std(ddof=0))
        if sd <= 0:
            return 0.0
        return float((arr[-1] - mu) / sd)

    def _spread_series(self) -> List[float]:
        n = min(len(self._prices_a), len(self._prices_b))
        return [
            a - self._hedge_ratio(list(self._prices_a), list(self._prices_b)) * b
            for a, b in zip(list(self._prices_a)[-n:], list(self._prices_b)[-n:])
        ]

    def step(self) -> Optional[Tuple[OrderSide, OrderSide]]:
        cfg = self.config
        if len(self._prices_a) < cfg.lookback or len(self._prices_b) < cfg.lookback:
            return None
        corr = self._correlation(list(self._prices_a), list(self._prices_b))
        if corr < cfg.min_correlation:
            return None
        spread = self._spread_series()
        z = self._zscore(spread)
        if z >= cfg.z_entry:
            return (OrderSide.SELL, OrderSide.BUY)
        if z <= -cfg.z_entry:
            return (OrderSide.BUY, OrderSide.SELL)
        if abs(z) <= cfg.z_exit:
            return (OrderSide.BUY, OrderSide.SELL)
        if abs(z) >= cfg.z_stop:
            return (OrderSide.BUY, OrderSide.SELL)
        return None

    def feed_and_signal(self, price_a: float, price_b: float) -> Optional[Tuple[OrderSide, OrderSide]]:
        self.feed(price_a, price_b)
        return self.step()


__all__ = ["StatArbConfig", "StatArbStrategy"]
