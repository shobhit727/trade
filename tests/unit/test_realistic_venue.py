from __future__ import annotations

from decimal import Decimal

import pytest

from cryptobot.core.events import OrderEvent, OrderSide, OrderStatus, OrderType
from cryptobot.execution.venue.realistic import (
    AdverseSelectionConfig,
    OrderBookSide,
    QueueModelConfig,
    RealisticVenue,
    RealisticVenueConfig,
)


def _venue(**overrides) -> RealisticVenue:
    overrides.setdefault("adverse_selection", AdverseSelectionConfig(enabled=False))
    overrides.setdefault("queue_model", QueueModelConfig(enabled=False))
    cfg = RealisticVenueConfig(
        initial_prices={"BTCUSDT": Decimal("65000")},
        maker_fee_bps=Decimal("1"),
        taker_fee_bps=Decimal("5"),
        **overrides,
    )
    return RealisticVenue(cfg)


def _order(side=OrderSide.BUY, type_=OrderType.MARKET, qty="1", price=None):
    return OrderEvent(
        symbol="BTCUSDT",
        side=side,
        type=type_,
        quantity=Decimal(qty),
        price=Decimal(price) if price else None,
        strategy="test",
    )


@pytest.mark.asyncio
async def test_market_order_fills_against_book():
    venue = _venue()
    order = _order()
    await venue.submit_order(order)
    assert order.status == OrderStatus.FILLED
    assert order.filled_quantity == Decimal("1")
    assert order.avg_fill_price is not None
    assert order.avg_fill_price > 0


@pytest.mark.asyncio
async def test_limit_order_fills_at_limit_price_not_slippage(monkeypatch):
    venue = _venue()
    monkeypatch.setattr("cryptobot.execution.venue.realistic.random.random", lambda: 0.0)
    mark = venue.book_sim.get_mid_price("BTCUSDT")
    limit_price = mark - Decimal("50")  # well inside the book
    order = _order(type_=OrderType.LIMIT, price=str(limit_price))
    await venue.submit_order(order)
    assert order.status == OrderStatus.FILLED
    # A limit buy must fill at its own price, never at the slippage-adjusted mark
    assert order.avg_fill_price == limit_price
    assert order.filled_quantity == Decimal("1")


@pytest.mark.asyncio
async def test_market_order_fee_uses_taker_rate():
    venue = _venue()
    order = _order(qty="2")
    await venue.submit_order(order)
    expected = order.filled_quantity * order.avg_fill_price * venue.config.taker_fee_bps / Decimal("10000")
    assert order.commission == expected.quantize(Decimal("0.0001"))


@pytest.mark.asyncio
async def test_partial_fill_quantity_is_ratio_based(monkeypatch):
    venue = _venue(queue_model=QueueModelConfig(enabled=True, min_fill_ratio=0.5, max_queue_position=10))
    monkeypatch.setattr("cryptobot.execution.venue.realistic.random.random", lambda: 0.0)
    order = _order(type_=OrderType.LIMIT, qty="10", price="64000")
    await venue.submit_order(order)
    # With queue position 0 but a ratio model, the filled qty is a fraction of qty
    assert order.filled_quantity > Decimal("0")
    assert order.filled_quantity <= Decimal("10")
    # commission on the *filled* qty only (maker rate)
    assert order.commission <= (order.filled_quantity * order.avg_fill_price * venue.config.maker_fee_bps / Decimal("10000")) + Decimal("0.0001")


@pytest.mark.asyncio
async def test_adverse_selection_moves_book_after_taker_fill():
    venue = _venue(adverse_selection=AdverseSelectionConfig(enabled=True, max_adverse_bps=Decimal("5")))
    mid_before = venue.book_sim.get_mid_price("BTCUSDT")
    order = _order(side=OrderSide.BUY)
    await venue.submit_order(order)
    mid_after = venue.book_sim.get_mid_price("BTCUSDT")
    # A buy fill with toxic flow pushes the mid DOWN
    assert mid_after < mid_before


@pytest.mark.asyncio
async def test_adverse_selection_skipped_when_disabled():
    venue = _venue(adverse_selection=AdverseSelectionConfig(enabled=False))
    mid_before = venue.book_sim.get_mid_price("BTCUSDT")
    order = _order(side=OrderSide.BUY)
    await venue.submit_order(order)
    mid_after = venue.book_sim.get_mid_price("BTCUSDT")
    assert mid_after == mid_before


def test_update_mid_price_preserves_resting_orders():
    venue = _venue()
    venue.book_sim.place_order("BTCUSDT", OrderSide.BUY, Decimal("64900"), Decimal("1"), "rest-1")
    assert len(venue.book_sim.books["BTCUSDT"][OrderBookSide.BID]) >= 2
    venue.book_sim.update_mid_price("BTCUSDT", Decimal("65100"))
    # the resting order must still be in the (shifted) book
    found = any(o.order_id == "rest-1" for side in venue.book_sim.books["BTCUSDT"].values() for lvl in side.values() for o in lvl.orders)
    assert found


def test_initial_book_has_liquidity():
    venue = _venue()
    best_ask_total = sum(lvl.total_quantity for lvl in venue.book_sim.books["BTCUSDT"][OrderBookSide.ASK].values())
    assert best_ask_total > 0


def test_initial_spread_configurable():
    venue = _venue(spreads={"BTCUSDT": Decimal("2")})
    assert venue.book_sim.get_spread("BTCUSDT") == Decimal("2")
