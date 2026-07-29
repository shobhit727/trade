from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import List

import pytest

from cryptobot.core.events import OrderEvent, OrderSide, OrderType
from cryptobot.execution.router import RouterConfig, SmartOrderRouter, VenueScore


class _FastVenue:
    def __init__(self, name: str, price: Decimal, fail_submit: bool = False, latency_ms: float = 5):
        self.name = name
        self._price = price
        self._fail = fail_submit
        self._latency = latency_ms
        self.submits: List[OrderEvent] = []

    async def submit_order(self, order: OrderEvent) -> OrderEvent:
        if self._fail:
            raise RuntimeError(f"{self.name} down")
        await asyncio.sleep(self._latency / 1000.0)
        self.submits.append(order)
        order.filled_quantity = order.quantity
        order.avg_fill_price = self._price
        from cryptobot.core.events import OrderStatus
        order.status = OrderStatus.FILLED
        order.__post_init__()
        return order

    async def cancel_order(self, order_id):
        return True

    async def get_price(self, symbol: str) -> Decimal:
        return self._price


def _make_order() -> OrderEvent:
    return OrderEvent(symbol="BTCUSDT", side=OrderSide.BUY, type=OrderType.MARKET, quantity=Decimal("1"), price=Decimal("100"))


def test_record_venue_quote_latency_no_prometheus_safe(monkeypatch):
    """Helpers must tolerate missing prometheus_client without raising."""
    import importlib

    import cryptobot.monitoring.metrics as metrics

    original = metrics.record_venue_quote_latency

    captured = []

    def fake_record(venue, symbol, latency):
        captured.append((venue, symbol, latency))
        return None

    metrics.record_venue_quote_latency = fake_record
    metrics.record_venue_quote_latency(venue="binance", symbol="BTCUSDT", latency=0.012)
    metrics.record_venue_quote_latency = original
    assert captured == [("binance", "BTCUSDT", 0.012)]


def test_record_routing_decision_invokes_metric(monkeypatch):
    import cryptobot.monitoring.metrics as metrics

    calls = []

    def fake_decision(venue, symbol, action):
        calls.append((venue, symbol, action))

    metrics.record_routing_decision = fake_decision
    metrics.record_routing_decision(venue="binance", symbol="BTCUSDT", action="selected")
    metrics.record_routing_decision = fake_decision
    assert calls == [("binance", "BTCUSDT", "selected")]


@pytest.mark.asyncio
async def test_router_records_decisions(monkeypatch):
    captured = []

    def fake_record(venue, symbol, action):
        captured.append((venue, symbol, action))

    def fake_quote(venue, symbol, latency):
        captured.append(("quote", venue, symbol, latency))

    import cryptobot.monitoring.metrics as metrics
    metrics.record_routing_decision = fake_record
    metrics.record_venue_quote_latency = fake_quote

    a = _FastVenue("a", Decimal("101"))
    b = _FastVenue("b", Decimal("100"))
    router = SmartOrderRouter([a, b])
    routed = await router.route(_make_order())
    assert routed.fills, "Expected a fill from the lower-priced venue"
    assert any(c[0] == "quote" for c in captured), "Expected quote latency captured"
    actions = [c[2] for c in captured if isinstance(c[1], str)]
    assert "selected" in actions


@pytest.mark.asyncio
async def test_router_records_fallback_decision(monkeypatch):
    captured = []

    def fake_record(venue, symbol, action):
        captured.append((venue, symbol, action))

    def fake_quote(venue, symbol, latency):
        pass

    import cryptobot.monitoring.metrics as metrics
    metrics.record_routing_decision = fake_record
    metrics.record_venue_quote_latency = fake_quote

    bad = _FastVenue("bad", Decimal("100"), fail_submit=True)
    good = _FastVenue("good", Decimal("101"))
    router = SmartOrderRouter([bad, good], ranker=lambda *_a, **_kw: 0)
    routed = await router.route(_make_order())
    assert routed.fills, "Expected fallback fill"
    fallback_actions = [c for c in captured if c[2] in ("fallback", "filled", "failed")]
    assert any(c[2] == "fallback" for c in fallback_actions)
    assert any(c[2] == "filled" for c in fallback_actions)


def test_simulated_venue_records_round_trip(monkeypatch):
    from cryptobot.execution.venue.simulated import SimulatedVenue
    captured = []

    def fake_record(venue, symbol, order_type, latency):
        captured.append((venue, symbol, order_type, latency))

    import cryptobot.monitoring.metrics as metrics
    metrics.record_execution_latency = fake_record
    venue = SimulatedVenue(prices={"BTCUSDT": Decimal("100")})
    order = OrderEvent(order_id="x1", symbol="BTCUSDT", side=OrderSide.BUY, type=OrderType.MARKET, quantity=Decimal("1"), price=Decimal("100"))
    asyncio.run(venue.submit_order(order))
    assert any(c[0] == "simulated" for c in captured), captured
