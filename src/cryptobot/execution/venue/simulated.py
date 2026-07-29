from __future__ import annotations

from decimal import Decimal

from cryptobot.core.events import OrderEvent, OrderStatus
from cryptobot.execution.venue.base import Venue


class SimulatedVenue(Venue):
    def __init__(self, prices: dict[str, Decimal] | None = None):
        self.prices = prices or {}
        self.orders: dict[str, OrderEvent] = {}

    async def submit_order(self, order: OrderEvent) -> OrderEvent:
        price = order.price or self.prices.get(order.symbol, Decimal("0"))
        order.status = OrderStatus.FILLED
        order.filled_quantity = order.quantity
        order.avg_fill_price = price
        order.__post_init__()
        self.orders[order.order_id] = order
        return order

    async def cancel_order(self, order_id: str) -> bool:
        order = self.orders.get(order_id)
        if not order:
            return False
        order.status = OrderStatus.CANCELED
        order.__post_init__()
        return True

    async def get_price(self, symbol: str) -> Decimal:
        return self.prices.get(symbol, Decimal("0"))


__all__ = ["SimulatedVenue"]
