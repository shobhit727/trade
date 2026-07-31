from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from decimal import Decimal

from cryptobot.core.events import OrderEvent, OrderStatus
from cryptobot.execution.venue.base import Venue

logger = logging.getLogger(__name__)


@dataclass
class FillResult:
    order_id: str
    symbol: str
    side: str
    filled_quantity: Decimal
    fill_price: Decimal
    fees: Decimal
    slippage_bps: Decimal
    funding_payment: Decimal


class SimulatedVenue(Venue):
    def __init__(
        self,
        prices: dict[str, Decimal] | None = None,
        slippage_bps: Decimal = Decimal("2"),
        commission_bps: Decimal = Decimal("5"),
        funding_rate: Decimal = Decimal("0.0001"),
    ):
        self.prices = prices or {}
        self.default_slippage_bps = slippage_bps
        self.commission_bps = commission_bps
        self.funding_rate = funding_rate
        self.orders: dict[str, OrderEvent] = {}
        self._position_qty: dict[str, Decimal] = {}

    async def submit_order(self, order: OrderEvent) -> OrderEvent:
        start = time.perf_counter()
        mark = order.price or self.prices.get(order.symbol, Decimal("0"))
        if mark <= 0:
            order.status = OrderStatus.REJECTED
            self.orders[order.order_id] = order
            order.__post_init__()
            return order
        slip = self.default_slippage_bps
        if order.side.value == "BUY":
            fill_price = mark * (Decimal("1") + slip / Decimal("10000"))
        else:
            fill_price = mark * (Decimal("1") - slip / Decimal("10000"))
        fill_price = fill_price.quantize(Decimal("0.0001"))
        fees = (order.quantity * fill_price * self.commission_bps / Decimal("10000")).quantize(Decimal("0.0001"))
        order.filled_quantity = order.quantity
        order.avg_fill_price = fill_price
        order.commission = fees
        order.status = OrderStatus.FILLED
        order.__post_init__()
        self.orders[order.order_id] = order
        pos = self._position_qty.get(order.symbol, Decimal("0"))
        if order.side.value == "BUY":
            self._position_qty[order.symbol] = pos + order.quantity
        else:
            self._position_qty[order.symbol] = pos - order.quantity
        self._record_round_trip("simulated", order.symbol, order.type.value, start)
        return order

    @staticmethod
    def _record_round_trip(venue: str, symbol: str, order_type: str, start: float) -> None:
        latency_ms = (time.perf_counter() - start) * 1000.0
        try:
            from cryptobot.monitoring.metrics import record_execution_latency
            record_execution_latency(venue=venue, symbol=symbol, order_type=order_type, latency=latency_ms / 1000.0)
        except Exception as exc:
            logger.debug("metrics record skipped: %s", exc)

    async def cancel_order(self, order_id: str) -> bool:
        order = self.orders.get(order_id)
        if not order:
            return False
        order.status = OrderStatus.CANCELED
        order.__post_init__()
        return True

    async def get_price(self, symbol: str) -> Decimal:
        return self.prices.get(symbol, Decimal("0"))


__all__ = ["SimulatedVenue", "FillResult"]
