"""Tests for the realistic paper venue: latency, partials, impact, queue."""

from __future__ import annotations

from decimal import Decimal

import pytest

from cryptobot.core.events import OrderEvent, OrderSide, OrderType
from cryptobot.execution.venue.realistic_sim import RealisticConfig, RealisticSimVenue


def _order(side=OrderSide.BUY, qty="100", otype=OrderType.MARKET, price=None):
    return OrderEvent(symbol="TEST", side=side, type=otype,
                      quantity=Decimal(qty), price=price)


def _venue(**cfg) -> RealisticSimVenue:
    slip = cfg.pop("slippage_bps", Decimal("1"))
    v = RealisticSimVenue(commission_bps=Decimal("2"), slippage_bps=slip,
                          config=RealisticConfig(latency_ms=1, **cfg))
    v.prices["TEST"] = Decimal("100")
    return v


@pytest.mark.asyncio
async def test_market_order_fills_with_latency_and_base_slip():
    v = _venue(slippage_bps=5)  # 5bps on 100 = exactly one 0.05 tick
    o = await v.submit_order(_order())
    assert o.status.value == "FILLED"
    assert o.avg_fill_price == Decimal("100.05")


@pytest.mark.asyncio
async def test_size_impact_increases_slippage():
    v = _venue(max_participation=0.02)
    v.set_reference_volume("TEST", 10_000.0)   # cap = 200 shares
    small = await v.submit_order(_order(qty="20"))
    big = await v.submit_order(_order(qty="200"))
    assert big.avg_fill_price > small.avg_fill_price > Decimal("100")
    assert v.stats["impact_fills"] >= 1


@pytest.mark.asyncio
async def test_partial_fill_then_drip():
    v = _venue(max_participation=0.02)
    v.set_reference_volume("TEST", 5_000.0)    # cap = 100 of 500 requested
    o = await v.submit_order(_order(qty="500"))
    assert o.filled_quantity == Decimal("100")
    assert o.status.value == "PARTIALLY_FILLED"
    done = v.advance_bar("TEST", Decimal("101"), 50_000.0)
    assert done, "remainder should drip on next bar"
    assert o.filled_quantity > Decimal("100")


@pytest.mark.asyncio
async def test_limit_requires_trade_through():
    v = _venue(queue_ticks=1)
    # SELL limit at 100 with mark exactly 100: not traded through -> rejected.
    o = await v.submit_order(_order(side=OrderSide.SELL, otype=OrderType.LIMIT,
                                    price="100"))
    assert o.status.value == "REJECTED"
    assert v.stats["queue_rejects"] == 1
    # Mark at 100.06 (>= 1 tick through): fills AT the limit price.
    v.prices["TEST"] = Decimal("100.06")
    o2 = await v.submit_order(_order(side=OrderSide.SELL, otype=OrderType.LIMIT,
                                     price="100"))
    assert o2.status.value == "FILLED"
    assert o2.avg_fill_price == Decimal("100.0")  # maker: no slip


@pytest.mark.asyncio
async def test_tick_quantization():
    v = _venue()
    v.prices["TEST"] = Decimal("100.013")
    o = await v.submit_order(_order())
    assert (o.avg_fill_price / Decimal("0.05")) % 1 == 0, "price must sit on tick grid"
