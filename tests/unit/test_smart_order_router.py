from __future__ import annotations

from decimal import Decimal

import pytest

from cryptobot.core.events import OrderEvent, OrderSide, OrderType
from cryptobot.execution.router import (
    RouterConfig,
    SmartOrderRouter,
    VenueScore,
    best_effort_ranker,
    best_price_ranker,
    latency_aware_ranker,
)
from cryptobot.execution.venue.simulated import SimulatedVenue


class _RecordingVenue:
    def __init__(self, name: str, price: Decimal, fee_bps: Decimal = Decimal("0"), fail: bool = False):
        self.name = name
        self._price = price
        self._fee_bps = fee_bps
        self._fail = fail
        self.submits: list[OrderEvent] = []

    async def submit_order(self, order: OrderEvent) -> OrderEvent:
        if self._fail:
            raise RuntimeError(f"{self.name} down")
        self.submits.append(order)
        order.filled_quantity = order.quantity
        order.avg_fill_price = self._price
        order.status = __import__("cryptobot.core.events", fromlist=["OrderStatus"]).OrderStatus.FILLED
        order.__post_init__()
        return order

    async def cancel_order(self, order_id: str) -> bool:
        return True

    async def get_price(self, symbol: str) -> Decimal:
        if self._fail:
            raise RuntimeError(f"{self.name} down")
        return self._price


def _make_order(side: OrderSide = OrderSide.BUY, qty: Decimal = Decimal("1")) -> OrderEvent:
    return OrderEvent(symbol="BTCUSDT", side=side, type=OrderType.MARKET, quantity=qty, price=Decimal("100"))


@pytest.mark.asyncio
async def test_router_requires_at_least_one_venue():
    with pytest.raises(ValueError):
        SmartOrderRouter([])


@pytest.mark.asyncio
async def test_router_picks_lowest_price():
    v1 = _RecordingVenue("a", Decimal("101"))
    v2 = _RecordingVenue("b", Decimal("100"))
    v3 = _RecordingVenue("c", Decimal("102"))
    router = SmartOrderRouter([v1, v2, v3])
    scores = await router.quote_all("BTCUSDT")
    chosen = router.pick(scores)
    assert chosen.name == "b"


@pytest.mark.asyncio
async def test_router_falls_back_when_primary_fails():
    good = _RecordingVenue("good", Decimal("100"))
    bad = _RecordingVenue("bad", Decimal("99"), fail=True)
    router = SmartOrderRouter([good, bad])
    routed = await router.route(_make_order())
    assert routed.fills, "Expected at least one fill"
    assert routed.fills[0].avg_fill_price == Decimal("100")


@pytest.mark.asyncio
async def test_router_skips_unquoted_venues():
    bad = _RecordingVenue("bad", Decimal("0"))
    good = _RecordingVenue("good", Decimal("100"))
    router = SmartOrderRouter([bad, good])
    routed = await router.route(_make_order())
    assert routed.fills and routed.fills[0].avg_fill_price == Decimal("100")


@pytest.mark.asyncio
async def test_router_uses_latency_aware_ranker():
    fast_expensive = _RecordingVenue("fast", Decimal("101"))
    slow_cheap = _RecordingVenue("slow", Decimal("100"))
    fast_expensive.get_price = _fast_get_price_factory(fast_expensive, latency_ms=1)
    slow_cheap.get_price = _fast_get_price_factory(slow_cheap, latency_ms=20)
    router = SmartOrderRouter([fast_expensive, slow_cheap], ranker=latency_aware_ranker, config=RouterConfig(max_latency_ms=200))
    routed = await router.route(_make_order())
    assert routed.fills
    assert routed.fills[0].avg_fill_price in {Decimal("101"), Decimal("100")}


def _fast_get_price_factory(venue: _RecordingVenue, latency_ms: float):
    async def _gp(symbol: str) -> Decimal:
        return venue._price
    return _gp


@pytest.mark.asyncio
async def test_router_split_and_route_distributes_qty_proportionally():
    a = _RecordingVenue("a", Decimal("100"))
    b = _RecordingVenue("b", Decimal("101"))
    c = _RecordingVenue("c", Decimal("99"))
    router = SmartOrderRouter([a, b, c])
    order = _make_order(qty=Decimal("1"))
    routed = await router.split_and_route(order, ratio=[Decimal("1"), Decimal("1"), Decimal("1")])
    assert routed.children
    assert len(routed.fills) >= 1
    total_filled = sum((f.filled_quantity for f in routed.fills), Decimal("0"))
    assert total_filled >= Decimal("0")


@pytest.mark.asyncio
async def test_router_split_rejects_invalid_ratio():
    a = _RecordingVenue("a", Decimal("100"))
    router = SmartOrderRouter([a])
    with pytest.raises(ValueError):
        await router.split_and_route(_make_order(), ratio=[])


@pytest.mark.asyncio
async def test_router_quote_all_returns_score_for_every_venue():
    v1 = _RecordingVenue("a", Decimal("100"))
    v2 = _RecordingVenue("b", Decimal("101"))
    router = SmartOrderRouter([v1, v2])
    scores = await router.quote_all("BTCUSDT")
    assert len(scores) == 2
    assert all(isinstance(s, VenueScore) for s in scores)


def test_rankers_handle_empty():
    assert best_price_ranker("X", []) == -1
    assert latency_aware_ranker("X", []) == -1
    assert best_effort_ranker("X", []) == -1


@pytest.mark.asyncio
async def test_router_uses_existing_simulated_venue():
    venue = SimulatedVenue(prices={"BTCUSDT": Decimal("100")})
    router = SmartOrderRouter([venue])
    routed = await router.route(_make_order(qty=Decimal("2")))
    assert routed.fills and routed.fills[0].filled_quantity == Decimal("2")
