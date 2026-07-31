from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from uuid import uuid4

from cryptobot.config import settings
from cryptobot.core.bus import EventBus, get_event_bus
from cryptobot.core.events import Event, EventType, OrderEvent, OrderStatus
from cryptobot.execution.router import SmartOrderRouter
from cryptobot.execution.venue.base import Venue
from cryptobot.execution.venue.simulated import SimulatedVenue
from cryptobot.risk.manager import RiskManager, get_risk_manager


def build_venue(mode: str | None = None) -> Venue:
    mode = (mode or settings.execution.mode or "paper").lower()
    if mode in {"paper", "backtest"}:
        return SimulatedVenue()
    if mode in {"testnet", "live", "binance"}:
        try:
            from cryptobot.execution.venue.binance import BinanceVenue
            return BinanceVenue()
        except Exception:
            return SimulatedVenue()
    return SimulatedVenue()


@dataclass
class ExecutionEngine:
    venue: Venue = field(default_factory=build_venue)
    risk_manager: RiskManager = field(default_factory=get_risk_manager)
    event_bus: EventBus = field(default_factory=get_event_bus)
    orders: dict[str, OrderEvent] = field(default_factory=dict)
    router: Optional[SmartOrderRouter] = None

    async def submit_order(self, order: OrderEvent) -> OrderEvent:
        if not order.order_id:
            order.order_id = str(uuid4())
        risk = self.risk_manager.check_order(order, order.price)
        await self.event_bus.publish(risk.to_event("pre_trade", order))
        if not risk.passed:
            order.status = OrderStatus.REJECTED
            order.__post_init__()
            self.orders[order.order_id] = order
            await self.event_bus.publish(Event(
                type=EventType.ORDER_REJECTED,
                source=order.strategy,
                correlation_id=order.order_id,
                payload={
                    "order": order.payload,
                    "reason": risk.message,
                    "check_type": "pre_trade",
                },
            ))
            return order

        if self.router is not None and len(self.router.venues) > 1:
            routed = await self.router.route(order)
            for child in routed.children:
                self.orders[child.order_id] = child
            first_fill = routed.fills[0] if routed.fills else None
            if first_fill is None:
                order.status = OrderStatus.REJECTED
                order.__post_init__()
                self.orders[order.order_id] = order
                await self.event_bus.publish(Event(
                    type=EventType.ORDER_REJECTED,
                    source=order.strategy,
                    correlation_id=order.order_id,
                    payload={"reason": "smart router found no fill", "check_type": "routing"},
                ))
                return order
            self.orders[first_fill.order_id] = first_fill
            await self.event_bus.publish(Event(type=EventType.ORDER_FILLED, payload=first_fill.payload))
            return first_fill

        filled = await self.venue.submit_order(order)
        self.orders[filled.order_id] = filled
        if filled.status == OrderStatus.REJECTED:
            await self.event_bus.publish(Event(
                type=EventType.ORDER_REJECTED,
                source=filled.strategy,
                correlation_id=filled.order_id,
                payload={"order": filled.payload, "reason": "venue rejected", "check_type": "venue"},
            ))
        else:
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


__all__ = ["ExecutionEngine", "build_venue", "get_execution_engine"]
