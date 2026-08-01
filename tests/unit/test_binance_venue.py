from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest

from cryptobot.core.events import OrderEvent, OrderSide, OrderStatus, OrderType


class FakeExchange:
    def __init__(self, responses: dict[str, Any] | None = None, errors: list[Exception] | None = None):
        self.create_order = AsyncMock(side_effect=errors or [responses or self._default()])
        self.cancel_order = AsyncMock(return_value=None)
        self.fetch_ticker = AsyncMock(return_value={"last": "101.5"})
        self.closed = False

    async def close(self):
        self.closed = True

    @staticmethod
    def _default() -> dict[str, Any]:
        return {
            "id": "binance-1",
            "status": "closed",
            "filled": 1.0,
            "amount": 1.0,
            "average": "100.5",
            "price": "100.5",
            "fee": {"cost": "0.01", "currency": "USDT"},
        }


@pytest.fixture
def fake_exchange(monkeypatch):
    import types
    
    # Create a mock instance
    fake_instance = FakeExchange()
    
    # Create a mock class that returns the instance
    fake_class = type("binance_fake", (), {"__new__": lambda cls, cfg: fake_instance})
    
    # Create a mock module for ccxt_async
    import cryptobot.execution.venue.binance as bmod
    mock_ccxt = types.ModuleType("ccxt.async_support")
    mock_ccxt.binance = fake_class
    monkeypatch.setattr(bmod, "ccxt_async", mock_ccxt, raising=False)
    return fake_instance


def _make_order(**kwargs) -> OrderEvent:
    defaults = dict(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        type=OrderType.MARKET,
        quantity=Decimal("1"),
        price=Decimal("100"),
    )
    defaults.update(kwargs)
    return OrderEvent(**defaults)


@pytest.mark.asyncio
async def test_rejects_when_credentials_missing(monkeypatch):
    monkeypatch.setenv("BINANCE_API_KEY", "")
    monkeypatch.setenv("BINANCE_API_SECRET", "")
    import importlib

    import cryptobot.config as cfgmod

    importlib.reload(cfgmod)
    import cryptobot.execution.venue.binance as bmod
    importlib.reload(bmod)

    venue = bmod.BinanceVenue(api_key="", api_secret="")
    order = _make_order()
    result = await venue.submit_order(order)
    assert result.status == OrderStatus.REJECTED
    assert "credentials" in result.payload.get("error", "").lower()
    importlib.reload(cfgmod)


@pytest.mark.asyncio
async def test_submit_order_returns_filled_event(fake_exchange, monkeypatch):
    monkeypatch.setenv("BINANCE_API_KEY", "testkey")
    monkeypatch.setenv("BINANCE_API_SECRET", "testsecret")
    import importlib

    import cryptobot.config as cfgmod
    importlib.reload(cfgmod)
    import cryptobot.execution.venue.binance as bmod
    importlib.reload(bmod)

    venue = bmod.BinanceVenue(api_key="k", api_secret="s")
    fake_exchange.create_order.return_value = FakeExchange._default()
    order = _make_order()
    filled = await venue.submit_order(order)
    assert filled.status == OrderStatus.FILLED
    assert filled.filled_quantity == Decimal("1")
    assert filled.avg_fill_price == Decimal("100.5")
    assert filled.commission == Decimal("0.01")
    assert filled.commission_asset == "USDT"
    importlib.reload(cfgmod)


@pytest.mark.asyncio
async def test_retries_then_rejects(fake_exchange, monkeypatch):
    monkeypatch.setenv("BINANCE_API_KEY", "k")
    monkeypatch.setenv("BINANCE_API_SECRET", "s")
    import importlib

    import cryptobot.config as cfgmod
    importlib.reload(cfgmod)
    import cryptobot.execution.venue.binance as bmod
    importlib.reload(bmod)

    venue = bmod.BinanceVenue(api_key="k", api_secret="s", max_retries=2)
    fake_exchange.create_order.side_effect = [RuntimeError("boom"), RuntimeError("boom")]
    order = _make_order()
    result = await venue.submit_order(order)
    assert result.status == OrderStatus.REJECTED
    assert "boom" in result.payload.get("error", "")
    importlib.reload(cfgmod)


@pytest.mark.asyncio
async def test_cancel_order_swallows_missing_credentials():
    import cryptobot.execution.venue.binance as bmod

    venue = bmod.BinanceVenue(api_key="", api_secret="")
    assert await venue.cancel_order("o1") is False


@pytest.mark.asyncio
async def test_get_price_returns_decimal(fake_exchange, monkeypatch):
    monkeypatch.setenv("BINANCE_API_KEY", "k")
    monkeypatch.setenv("BINANCE_API_SECRET", "s")
    import importlib

    import cryptobot.config as cfgmod
    importlib.reload(cfgmod)
    import cryptobot.execution.venue.binance as bmod
    importlib.reload(bmod)

    venue = bmod.BinanceVenue(api_key="k", api_secret="s")
    fake_exchange.fetch_ticker.return_value = {"last": 123.45}
    price = await venue.get_price("BTCUSDT")
    assert price == Decimal("123.45")
    importlib.reload(cfgmod)


def test_map_symbol_adds_slash():
    import cryptobot.execution.venue.binance as bmod

    venue = bmod.BinanceVenue(api_key="k", api_secret="s")
    assert venue._map_symbol("BTCUSDT") == "BTC/USDT"
    assert venue._map_symbol("ETH/USDT") == "ETH/USDT"
