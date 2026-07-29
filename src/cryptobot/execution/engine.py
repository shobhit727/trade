from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from cryptobot.core.bus import EventBus, get_event_bus
from cryptobot.core.events import Event, EventType, OrderEvent, OrderStatus
from cryptobot.execution.venue.base import Venue
from cryptobot.execution.venue.simulated import SimulatedVenue
from cryptobot.risk.manager import RiskManager, get_risk_manager


@dataclass
class ExecutionEngine:
    venue: Venue = field(default_factory=SimulatedVenue)
    risk_manager: RiskManager = field(default_factory=get_risk_manager)
    event_bus: EventBus = field(default_factory=get_event_bus)
    orders: dict[str, OrderEvent] = field(default_factory=dict)

    async def submit_order(self, order: OrderEvent) -> OrderEvent:
        if not order.order_id:
            order.order_id = str(uuid4())
        risk = self.risk_manager.check_order(order, order.price)
        await self.event_bus.publish(risk.to_event("pre_trade", order))
        if not risk.passed:
            order.status = OrderStatus.REJECTED
            order.__post_init__()
            self.orders[order.order_id] = order
            await self.event_bus.publish(order)
            return order

        filled = await self.venue.submit_order(order)
        self.orders[filled.order_id] = filled
        await self.event_bus.publish(Event(type=EventType.ORDER_FILLED, payload=filled.payload))
        return filled

    async def cancel_order(self, order_id: str) -> bool:
        cancelled = await self.venue.cancel_order(order_id)
        order = self.orders.get(order_id)
        if cancelled and order:
            order.status = OrderStatus.CANCELED
            order.__post_init__()
            await self.event_bus.publish(order)
        return cancelled


_execution_engine: ExecutionEngine | None = None


def get_execution_engine() -> ExecutionEngine:
    global _execution_engine
    if _execution_engine is None:
        _execution_engine = ExecutionEngine()
    return _execution_engine


__all__ = ["ExecutionEngine", "get_execution_engine"]
