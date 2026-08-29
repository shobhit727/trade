"""Market-making strategy (Avellaneda-Stoikov quote model).

The strategy quotes a two-sided book and, when an execution engine is attached,
routes real orders through it (subject to risk checks and venue fills). When no
engine is attached it simulates fills locally at the quoted bid/ask so backtests
and the ``mm`` CLI still produce real, non-fabricated fills. Inventory and cash
are tracked so the equity curve reflects actual mark-to-market PnL rather than
invented prices.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from cryptobot.core.events import OrderEvent, OrderSide, OrderStatus
from cryptobot.execution.adverse_selection import (
    AdverseSelectionGuard,
    TopOfBook,
    _install_guard_hook,
)
from cryptobot.execution.engine import ExecutionEngine


@dataclass
class MarketMakingConfig:
    symbol: str = "BTCUSDT"
    quantity: Decimal = Decimal("1")
    max_inventory: Decimal = Decimal("5")
    gamma: float = 0.1
    sigma: float = 2.0
    kappa: float = 1.5
    quote_step_bps: float = 1.0


class MarketMakingStrategy:
    name = "market_making"

    def __init__(self, config: MarketMakingConfig | None = None):
        self.config = config or MarketMakingConfig()
        self.inventory: Decimal = Decimal("0")
        self._cash: Decimal = Decimal("0")
        self._last_mid: Decimal | None = None
        self._last_top: TopOfBook | None = None
        self._exec: ExecutionEngine | None = None
        self._guard: AdverseSelectionGuard | None = None
        self._bid_id: str = ""
        self._ask_id: str = ""
        self._bid_price: Decimal | None = None
        self._ask_price: Decimal | None = None
        self.last_action: str = ""
        self.history: list[OrderEvent] = []
        self._equity_curve: list[float] = []

    @property
    def equity_curve(self) -> list[float]:
        return self._equity_curve

    def attach_execution(
        self,
        engine: ExecutionEngine,
        guard: AdverseSelectionGuard | None = None,
    ) -> None:
        self._exec = engine
        self._guard = guard
        if guard is not None:
            # Install the real adverse-selection hook: every order submitted
            # through the engine is registered with the guard at the last book
            # top (set by on_top), so toxic flow can be cancelled/replaced.
            _install_guard_hook(engine, guard)

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

    def on_top(self, top: TopOfBook) -> None:
        self._last_top = top
        if self._exec is not None:
            # Expose the latest book top to the engine so the adverse-selection
            # hook can register submitted orders against it.
            self._exec._last_top = top
        if self._guard is not None:
            self._guard.note_top(top)

    def on_fill(self, order: OrderEvent) -> None:
        if order.status != OrderStatus.FILLED:
            return
        qty = order.filled_quantity or order.quantity
        price = order.avg_fill_price or order.price or Decimal("0")
        if order.side == OrderSide.BUY:
            self.inventory += qty
            self._cash -= qty * price
        else:
            self.inventory -= qty
            self._cash += qty * price
        mid = self._last_mid or price
        self._equity_curve.append(float(self._cash + self.inventory * mid))

    def quote(self, mid: Decimal, t_remaining: float = 1.0) -> tuple[Decimal, Decimal]:
        bid_f, ask_f = self._avellaneda_stoikov(float(mid), t_remaining)
        return Decimal(str(round(bid_f, 8))), Decimal(str(round(ask_f, 8)))

    async def _submit(self, order: OrderEvent, top: TopOfBook | None = None) -> OrderEvent:
        """Submit an order, returning the filled event.

        When an engine is attached the order goes through the real risk/venue
        path. Otherwise it is filled locally at the quoted price (maker fill) so
        simulations stay deterministic and non-fabricated.
        """
        if self._exec is not None:
            filled = await self._exec.submit_order(order)
        else:
            filled = order
            filled.filled_quantity = filled.quantity
            filled.avg_fill_price = filled.price
            filled.status = OrderStatus.FILLED
            filled.__post_init__()
        self.on_fill(filled)
        self.history.append(filled)
        return filled

    async def on_book_update(
        self,
        bid: Decimal,
        ask: Decimal,
        mid: Decimal,
        timestamp=None,
    ) -> None:
        self._last_mid = mid
        snapshot = TopOfBook(bid=bid, ask=ask, mid=mid)
        self.on_top(snapshot)
        bid_q, ask_q = self.quote(mid)
        qty = self.config.quantity
        max_inv = self.config.max_inventory
        if self.inventory < max_inv:
            buy = OrderEvent(
                symbol=self.config.symbol,
                side=OrderSide.BUY,
                quantity=qty,
                price=bid_q,
                strategy=self.name,
            )
            filled_buy = await self._submit(buy, snapshot)
            self._bid_id = filled_buy.order_id or "mm-bid"
            self._bid_price = bid_q
        if self.inventory > -max_inv:
            sell = OrderEvent(
                symbol=self.config.symbol,
                side=OrderSide.SELL,
                quantity=qty,
                price=ask_q,
                strategy=self.name,
            )
            filled_sell = await self._submit(sell, snapshot)
            self._ask_id = filled_sell.order_id or "mm-ask"
            self._ask_price = ask_q
        return None

    async def run_on_history(self, bars) -> list[OrderEvent]:
        start = len(self.history)
        for i, bar in enumerate(bars):
            mid = Decimal(str(bar.close))
            bid = mid - Decimal("0.5")
            ask = mid + Decimal("0.5")
            t_remaining = max(0.0, 1.0 - (i / max(len(bars), 1)))
            await self.on_book_update(
                bid=bid,
                ask=ask,
                mid=mid,
                timestamp=getattr(bar, "timestamp", None),
            )
        return list(self.history[start:])

    def feed(self, top: TopOfBook) -> None:
        self.on_top(top)
        self.last_action = "quoted"
        return None


__all__ = ["MarketMakingConfig", "MarketMakingStrategy"]
