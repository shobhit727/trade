from __future__ import annotations

import pytest

from cryptobot.execution.venue.binance import BinanceVenue


def test_binance_venue_init_defaults():
    v = BinanceVenue()
    assert v.market_type == "future"
    assert v.rate_limit_ms == 200
    assert v.max_retries == 3
    assert v._exchange is None


def test_binance_venue_init_custom():
    v = BinanceVenue(
        api_key="test_key",
        api_secret="test_secret",
        market_type="spot",
        sandbox=True,
        rate_limit_ms=100,
        max_retries=5,
    )
    assert v.api_key == "test_key"
    assert v.api_secret == "test_secret"
    assert v.market_type == "spot"
    assert v.sandbox is True
    assert v.rate_limit_ms == 100
    assert v.max_retries == 5


def test_binance_venue_map_order_type():
    from cryptobot.core.events import OrderType
    v = BinanceVenue()
    assert v._map_order_type(OrderType.MARKET) == "market"
    assert v._map_order_type(OrderType.LIMIT) == "limit"
    assert v._map_order_type(OrderType.STOP_LOSS) == "stop_market"
    assert v._map_order_type(OrderType.STOP_LOSS_LIMIT) == "stop"
    assert v._map_order_type(OrderType.TAKE_PROFIT) == "take_profit_market"
    assert v._map_order_type(OrderType.TAKE_PROFIT_LIMIT) == "take_profit"


def test_binance_venue_map_side():
    from cryptobot.core.events import OrderSide
    v = BinanceVenue()
    assert v._map_side(OrderSide.BUY) == "buy"
    assert v._map_side(OrderSide.SELL) == "sell"


def test_binance_venue_has_credentials():
    v = BinanceVenue(api_key="key", api_secret="secret")
    assert v._has_credentials("key", "secret") is True
    assert v._has_credentials("", "secret") is False
    assert v._has_credentials("key", "") is False
    assert v._has_credentials("", "") is False


def test_binance_venue_reject():

    from cryptobot.core.events import OrderEvent, OrderSide, OrderStatus, OrderType
    v = BinanceVenue()
    order = OrderEvent(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        type=OrderType.MARKET,
        quantity=1,
    )
    rejected = v._reject(order, OrderStatus.REJECTED, "test reason")
    assert rejected.status == OrderStatus.REJECTED
    assert rejected.payload.get("error") == "test reason"


def test_binance_venue_close_without_exchange():
    import asyncio
    v = BinanceVenue()
    asyncio.run(v.close())
    # _closed only set if _exchange was not None
    assert v._closed is False
    assert v._exchange is None


def test_binance_venue_ensure_exchange_no_ccxt():
    import cryptobot.execution.venue.binance as binance_mod
    original = binance_mod.ccxt_async
    binance_mod.ccxt_async = None
    try:
        v = BinanceVenue()
        with pytest.raises(RuntimeError, match="ccxt is not installed"):
            v._ensure_exchange()
    finally:
        binance_mod.ccxt_async = original


__all__ = []
