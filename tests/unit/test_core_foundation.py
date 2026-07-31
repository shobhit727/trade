from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from cryptobot.backtest.engine import BacktestEngine
from cryptobot.core.bus import EventBus
from cryptobot.core.events import Event, EventType, OrderEvent, OrderSide, OrderType
from cryptobot.execution.engine import ExecutionEngine
from cryptobot.execution.venue.simulated import SimulatedVenue
from cryptobot.risk.manager import RiskManager
from cryptobot.utils.decorators import retry


@pytest.mark.asyncio
async def test_event_bus_subscription_and_history():
    bus = EventBus(max_history=10)
    seen: list[Event] = []

    async def handler(event: Event) -> None:
        seen.append(event)

    sub_id = await bus.subscribe(EventType.TICKER, async_callback=handler)
    event = Event(type=EventType.TICKER, payload={"symbol": "BTCUSDT", "price": "100"})

    delivered = await bus.publish(event)

    assert delivered == 1
    assert seen == [event]
    assert bus.get_history(event_type=EventType.TICKER) == [event]
    assert await bus.unsubscribe(sub_id) is True


@pytest.mark.asyncio
async def test_retry_decorator():
    attempts = 0

    @retry(max_attempts=3, backoff_factor=0)
    async def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectionError("temporary failure")
        return "ok"

    assert await flaky() == "ok"
    assert attempts == 3


@pytest.mark.asyncio
async def test_execution_engine_simulated_fill():
    venue = SimulatedVenue(prices={"BTCUSDT": Decimal("100")})
    engine = ExecutionEngine(venue=venue, risk_manager=RiskManager())
    order = OrderEvent(
        symbol="BTCUSDT",
        type=OrderType.MARKET,
        side=OrderSide.BUY,
        quantity=Decimal("1"),
        strategy="smoke",
    )

    filled = await engine.submit_order(order)

    assert filled.filled_quantity == Decimal("1")
    assert filled.avg_fill_price == Decimal("100")


@pytest.mark.asyncio
async def test_backtest_toy_fill_flow():
    async def stream():
        yield Event(
            type=EventType.ORDER_FILLED,
            timestamp=datetime(2024, 1, 1),
            payload={"symbol": "BTCUSDT", "filled_quantity": "1", "avg_fill_price": "100", "side": "BUY", "strategy": "smoke"},
        )
        yield Event(
            type=EventType.TICKER,
            timestamp=datetime(2024, 1, 2),
            payload={"symbol": "BTCUSDT", "price": "110"},
        )
        yield Event(
            type=EventType.ORDER_FILLED,
            timestamp=datetime(2024, 1, 3),
            payload={"symbol": "BTCUSDT", "filled_quantity": "1", "avg_fill_price": "110", "side": "SELL", "strategy": "smoke"},
        )

    engine = BacktestEngine(datetime(2024, 1, 1), datetime(2024, 1, 4), 10000)
    result = await engine.run(stream())

    assert result.total_trades == 1
    assert engine.get_trades()[0].pnl == Decimal("10")
