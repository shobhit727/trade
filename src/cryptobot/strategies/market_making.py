from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from decimal import Decimal

from cryptobot.core.events import OrderEvent, OrderSide, OrderStatus
from cryptobot.execution.adverse_selection import AdverseSelectionGuard, TopOfBook
from cryptobot.execution.engine import ExecutionEngine


@dataclass
class MarketMakingConfig:
    symbol: str = "BTCUSDT"
    gamma: float = 0.5
    sigma: float = 0.01
    kappa: float = 1.5
    A: float = 0.025
    max_inventory: Decimal = Decimal("5")
    quote_step_bps: float = 1.0
    min_quote_size: Decimal = Decimal("0.001")
    quantity: Decimal = Decimal("1")
    cancel_threshold_bps: float = 5.0


class MarketMakingStrategy:
    name = "market_making"

    def __init__(self, config: MarketMakingConfig | None = None):
        self.config = config or MarketMakingConfig()
        self.inventory: Decimal = Decimal("0")
        self._bid_price: Decimal | None = None
        self._ask_price: Decimal | None = None
        self._bid_id: str | None = None
        self._ask_id: str | None = None
        self._exec: ExecutionEngine | None = None
        self._guard: AdverseSelectionGuard | None = None
        self._last_mid: Decimal | None = None
        self._last_top: TopOfBook | None = None
        self._equity_curve: deque[float] = deque(maxlen=10_000)
        self.history: list[OrderEvent] = []

    def attach_execution(
        self,
        engine: ExecutionEngine,
        guard: AdverseSelectionGuard | None = None,
    ) -> None:
        self._exec = engine
        self._guard = guard

    def _avellaneda_stoikov(self, mid: float, t_remaining: float) -> tuple[float, float]:
        gamma = self.config.gamma
        sigma = self.config.sigma
        kappa = self.config.kappa
        reservation = mid - (self._inventory_to_float() * gamma * sigma * sigma * t_remaining)
        spread = (gamma * sigma * sigma * t_remaining) + ((2.0 / gamma) * math.log1p(gamma / kappa))
        half = max(spread / 2.0, self.config.quote_step_bps / 10_000.0 * mid)
        bid = reservation - half
        ask = reservation + half
        return bid, ask

    def _inventory_to_float(self) -> float:
        return float(self.inventory)

    def _step(self, ts, bid: Decimal, ask: Decimal, qty: Decimal) -> None:
        if qty <= 0:
            return
        if abs(self.inventory) >= float(self.config.max_inventory):
            return
        order = OrderEvent(
            symbol=self.config.symbol,
            side=OrderSide.SELL if self._last_mid and bid > self._last_mid else OrderSide.BUY,
            quantity=qty,
            price=ask if (self._last_mid and bid > self._last_mid) else bid,
            strategy=self.name,
        )
        if order.side == OrderSide.SELL:
            if self.inventory - order.quantity < Decimal("0"):
                return
        else:
            if self.inventory + order.quantity > self.config.max_inventory:
                return
        self.history.append(order)

    def on_top(self, top: TopOfBook) -> None:
        self._last_top = top
        if self._guard is not None:
            self._guard.note_top(top)

    def on_fill(self, order: OrderEvent) -> None:
        if order.status != OrderStatus.FILLED:
            return
        qty = order.filled_quantity or order.quantity
        if order.side == OrderSide.BUY:
            self.inventory += qty
        else:
            self.inventory -= qty

    def quote(self, mid: Decimal, t_remaining: float = 1.0) -> tuple[Decimal, Decimal]:
        bid_f, ask_f = self._avellaneda_stoikov(float(mid), t_remaining)
        return Decimal(str(round(bid_f, 8))), Decimal(str(round(ask_f, 8)))

    async def on_book_update(
        self,
        bid: Decimal,
        ask: Decimal,
        mid: Decimal,
        timestamp,
    ) -> None:
        self._last_mid = mid
        snapshot = TopOfBook(bid=bid, ask=ask, mid=mid)
        self.on_top(snapshot)
        bid_q, ask_q = self.quote(mid)
        qty = self.config.quantity
        if self._exec is not None and abs(self.inventory) < float(self.config.max_inventory):
            buy = OrderEvent(
                symbol=self.config.symbol,
                side=OrderSide.BUY,
                quantity=qty,
                price=bid_q,
                strategy=self.name,
            )
            sell = OrderEvent(
                symbol=self.config.symbol,
                side=OrderSide.SELL,
                quantity=qty,
                price=ask_q,
                strategy=self.name,
            )
            self._bid_id = buy.order_id or "mm-bid"
            self._ask_id = sell.order_id or "mm-ask"
            self._bid_price = bid_q
            self._ask_price = ask_q
            if self._guard is not None:
                self._guard.register(buy, snapshot)
                self._guard.register(sell, snapshot)
        return None

    def run_on_history(self, bars) -> list[OrderEvent]:
        fills: list[OrderEvent] = []
        for i, bar in enumerate(bars):
            mid = Decimal(str(bar.close))
            bid = mid - Decimal("0.5")
            ask = mid + Decimal("0.5")
            ts = getattr(bar, "timestamp", None)
            t_remaining = max(0.0, 1.0 - (i / max(len(bars), 1)))
            bid_q, ask_q = self.quote(mid, t_remaining)
            self.on_top(TopOfBook(bid=bid, ask=ask, mid=mid))
            self.on_book_update(bid=bid, ask=ask, mid=mid, timestamp=ts)

            if i % 2 == 0:
                self._step(ts, bid_q, ask_q, qty=self.config.quantity)
            if abs(self.inventory) >= float(self.config.max_inventory):
                pass
            if i % 2 == 1:
                self._step(ts, bid_q, ask_q, qty=self.config.quantity)

            fill = OrderEvent(
                symbol=self.config.symbol,
                side=OrderSide.BUY if i % 4 < 2 else OrderSide.SELL,
                quantity=self.config.quantity,
                price=bid_q if i % 4 < 2 else ask_q,
                strategy=self.name,
            )
            fill.filled_quantity = fill.quantity
            fill.avg_fill_price = bid_q if i % 4 < 2 else ask_q
            fill.status = OrderStatus.FILLED
            fill.__post_init__()
            self.on_fill(fill)
            fills.append(fill)
            self._equity_curve.append(float(fill.avg_fill_price or 0))
        return fills


__all__ = ["MarketMakingConfig", "MarketMakingStrategy"]
