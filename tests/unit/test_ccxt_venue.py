"""Unit tests for the generic ccxt venue adapter (Seed Phase step 2).

No network: the internal ``_exchange`` handle is replaced with fakes, and
ccxt itself is not required to be installed for any test here.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from cryptobot.core.events import OrderEvent, OrderSide, OrderStatus, OrderType
from cryptobot.execution.venue.binance import BinanceVenue
from cryptobot.execution.venue.ccxt_venue import CcxtVenue


def make_order(**overrides) -> OrderEvent:
    defaults: dict[str, Any] = {
        "symbol": "BTCUSDT",
        "side": OrderSide.BUY,
        "type": OrderType.MARKET,
        "quantity": Decimal("0.01"),
        "price": None,
    }
    defaults.update(overrides)
    return OrderEvent(**defaults)


@pytest.fixture(autouse=True)
def _fake_ccxt_module(monkeypatch):
    """Pretend ccxt is installed so venue methods reach our fakes."""
    monkeypatch.setattr("cryptobot.execution.venue.ccxt_venue.ccxt_async", object())


class FakeExchange:
    """Records calls; returns canned create_order responses."""

    def __init__(self, response=None, error: Exception | None = None):
        self.calls: list[tuple] = []
        self.cancel_calls: list[str] = []
        self.ticker_calls: list[str] = []
        self.response = response if response is not None else {
            "id": "exch-123", "status": "closed", "filled": "0.01",
            "average": "50000.0", "fee": {"cost": "0.5", "currency": "USDT"},
        }
        self.error = error

    async def create_order(self, symbol, type_, side, amount, price, params):
        self.calls.append((symbol, type_, side, amount, price, dict(params)))
        if self.error is not None:
            raise self.error
        return self.response

    async def cancel_order(self, order_id):
        self.cancel_calls.append(order_id)
        return {"status": "canceled"}

    async def fetch_ticker(self, symbol):
        self.ticker_calls.append(symbol)
        return {"last": "51000.5", "close": "50999.0"}

    async def close(self):
        pass


# ------------------------------------------------------------------- mapping


def test_symbol_mapping_generic():
    v = CcxtVenue(exchange_id="bybit")
    assert v._map_symbol("BTCUSDT") == "BTC/USDT"
    assert v._map_symbol("ETHUSDC") == "ETH/USDC"
    assert v._map_symbol("BTC/USDT") == "BTC/USDT"  # already unified
    assert v._map_symbol("WEIRD") == "WEIRD"  # unknown quote passthrough


def test_order_type_map_per_exchange():
    binance = CcxtVenue(exchange_id="binance")
    bybit = CcxtVenue(exchange_id="bybit")
    unknown = CcxtVenue(exchange_id="kraken")
    from cryptobot.core.events import OrderType

    assert binance._map_order_type(OrderType.STOP_LOSS) == "stop_market"
    assert bybit._map_order_type(OrderType.STOP_LOSS) == "market"
    assert unknown._map_order_type(OrderType.STOP_LOSS) == "stop_market"  # default table


def test_side_mapping():
    v = CcxtVenue(exchange_id="okx")
    assert v._map_side(OrderSide.BUY) == "buy"
    assert v._map_side(OrderSide.SELL) == "sell"


# -------------------------------------------------------------- submit paths


@pytest.mark.asyncio
async def test_submit_rejected_without_credentials():
    v = CcxtVenue(exchange_id="bybit", api_key="", api_secret="")
    result = await v.submit_order(make_order())
    assert result.status == OrderStatus.REJECTED
    assert "credentials missing" in result.payload["error"]


@pytest.mark.asyncio
async def test_submit_success_applies_fill(monkeypatch):
    v = CcxtVenue(exchange_id="bybit", api_key="k", api_secret="s")
    fake = FakeExchange()
    v._exchange = fake  # bypass _ensure_exchange

    order = make_order(client_order_id="cid-1")
    result = await v.submit_order(order)

    assert result.status == OrderStatus.FILLED
    assert result.order_id == "exch-123"
    assert result.filled_quantity == Decimal("0.01")
    assert result.avg_fill_price == Decimal("50000.0")
    assert result.commission == Decimal("0.5")
    assert result.commission_asset == "USDT"
    symbol, type_, side, amount, price, params = fake.calls[0]
    assert (symbol, type_, side) == ("BTC/USDT", "market", "buy")
    assert params.get("newClientOrderId") == "cid-1"


@pytest.mark.asyncio
async def test_submit_limit_without_price_rejected():
    v = CcxtVenue(exchange_id="bybit", api_key="k", api_secret="s")
    v._exchange = FakeExchange()
    result = await v.submit_order(make_order(type=OrderType.LIMIT, price=None))
    assert result.status == OrderStatus.REJECTED
    assert "missing price" in result.payload["error"].lower()


@pytest.mark.asyncio
async def test_submit_limit_with_price_sends_price():
    v = CcxtVenue(exchange_id="kraken", api_key="k", api_secret="s")
    fake = FakeExchange()
    v._exchange = fake
    result = await v.submit_order(
        make_order(type=OrderType.LIMIT, price=Decimal("49000.5"))
    )
    assert result.status == OrderStatus.FILLED
    assert fake.calls[0][4] == 49000.5


@pytest.mark.asyncio
async def test_submit_retries_then_rejects(monkeypatch):
    v = CcxtVenue(exchange_id="bybit", api_key="k", api_secret="s", max_retries=3)
    fake = FakeExchange(error=RuntimeError("network down"))
    v._exchange = fake
    sleeps: list[float] = []
    monkeypatch.setattr(
        "cryptobot.execution.venue.ccxt_venue.asyncio.sleep",
        lambda s: sleeps.append(s) or _noop(),
    )
    result = await v.submit_order(make_order())
    assert result.status == OrderStatus.REJECTED
    assert "network down" in result.payload["error"]
    assert len(fake.calls) == 3  # max_retries attempts
    assert sleeps[0] == 0.5 and sleeps[1] == 1.0 and len(sleeps) == 3  # backoff after each attempt


async def _noop():
    return None


@pytest.mark.asyncio
async def test_submit_unknown_exchange_id_rejected(monkeypatch):
    v = CcxtVenue(exchange_id="not_an_exchange", api_key="k", api_secret="s")
    result = await v.submit_order(make_order())
    assert result.status == OrderStatus.REJECTED
    assert "unknown ccxt exchange id" in result.payload["error"]


@pytest.mark.asyncio
async def test_reduce_only_param_passed():
    v = CcxtVenue(exchange_id="binance", api_key="k", api_secret="s")
    fake = FakeExchange()
    v._exchange = fake
    await v.submit_order(make_order(reduce_only=True))
    assert fake.calls[0][5].get("reduceOnly") is True


# ------------------------------------------------------------ cancel / quote


@pytest.mark.asyncio
async def test_cancel_order_success_and_failure():
    v = CcxtVenue(exchange_id="bybit", api_key="k", api_secret="s")
    fake = FakeExchange()
    v._exchange = fake
    assert await v.cancel_order("oid-1") is True
    assert fake.cancel_calls == ["oid-1"]

    class Boom(FakeExchange):
        async def cancel_order(self, order_id):
            raise RuntimeError("nope")

    v2 = CcxtVenue(exchange_id="bybit", api_key="k", api_secret="s")
    v2._exchange = Boom()
    assert await v2.cancel_order("oid-2") is False


@pytest.mark.asyncio
async def test_cancel_without_credentials_is_false():
    v = CcxtVenue(exchange_id="bybit", api_key="", api_secret="")
    assert await v.cancel_order("x") is False


@pytest.mark.asyncio
async def test_get_price_prefers_last():
    v = CcxtVenue(exchange_id="bybit", api_key="k", api_secret="s")
    fake = FakeExchange()
    v._exchange = fake
    price = await v.get_price("BTCUSDT")
    assert price == Decimal("51000.5")
    assert fake.ticker_calls == ["BTC/USDT"]


@pytest.mark.asyncio
async def test_get_price_zero_on_error_or_no_creds():
    v = CcxtVenue(exchange_id="bybit", api_key="", api_secret="")
    assert await v.get_price("BTCUSDT") == Decimal("0")

    class TickerBoom(FakeExchange):
        async def fetch_ticker(self, symbol):
            raise RuntimeError("down")

    v2 = CcxtVenue(exchange_id="bybit", api_key="k", api_secret="s")
    v2._exchange = TickerBoom()
    assert await v2.get_price("BTCUSDT") == Decimal("0")


# ------------------------------------------------------- subclass + factory


def test_binance_venue_is_ccxt_venue_specialization():
    v = BinanceVenue(api_key="k", api_secret="s")
    assert isinstance(v, CcxtVenue)
    assert v.exchange_id == "binance"
    assert v.market_type == "future"
    assert v.rate_limit_ms == 200
    assert v.max_retries == 3


def test_factory_selects_generic_ccxt_for_other_exchanges():
    from cryptobot.execution.engine import build_venue

    venue = build_venue("live", exchange_id="ByBit")
    assert isinstance(venue, CcxtVenue)
    assert venue.exchange_id == "bybit"


def test_factory_keeps_binance_class_for_binance():
    from cryptobot.execution.engine import build_venue

    venue = build_venue("live", exchange_id="binance")
    assert isinstance(venue, BinanceVenue)


def test_factory_paper_mode_ignores_exchange_id():
    from cryptobot.execution.engine import build_venue
    from cryptobot.execution.venue.simulated import SimulatedVenue

    assert isinstance(build_venue("paper", exchange_id="bybit"), SimulatedVenue)


# ------------------------------------------------------- protective stops


@pytest.mark.asyncio
async def test_place_protective_stop_success():
    v = CcxtVenue(exchange_id="bybit", api_key="k", api_secret="s")
    fake = FakeExchange()
    v._exchange = fake

    class StopResp(dict):
        pass

    async def create_order(symbol, type_, side, amount, price, params):
        fake.calls.append((symbol, type_, side, amount, price, dict(params)))
        return {"id": "stop-1"}

    fake.create_order = create_order
    oid = await v.place_protective_stop("BTCUSDT", "sell", 0.01, 45000.0)
    assert oid == "stop-1"
    symbol, type_, side, qty, price, params = fake.calls[0]
    assert (symbol, side) == ("BTC/USDT", "sell")
    assert params["reduceOnly"] is True and params["stopPrice"] == 45000.0


@pytest.mark.asyncio
async def test_place_protective_stop_binance_type():
    v = CcxtVenue(exchange_id="binance", api_key="k", api_secret="s")
    fake = FakeExchange()

    async def create_order(symbol, type_, side, amount, price, params):
        fake.calls.append((symbol, type_, side))
        return {"id": "s2"}

    fake.create_order = create_order
    v._exchange = fake
    await v.place_protective_stop("ETHUSDT", "buy", 1.0, 3000.0)
    assert fake.calls[0][1] == "stop_market"  # binance-specific type name


@pytest.mark.asyncio
async def test_place_protective_stop_failure_returns_none():
    v = CcxtVenue(exchange_id="bybit", api_key="k", api_secret="s")

    class Boom(FakeExchange):
        async def create_order(self, *a):
            raise RuntimeError("rejected")

    v._exchange = Boom()
    assert await v.place_protective_stop("BTCUSDT", "sell", 1.0, 1.0) is None


@pytest.mark.asyncio
async def test_place_protective_stop_no_creds_returns_none():
    v = CcxtVenue(exchange_id="bybit", api_key="", api_secret="")
    assert await v.place_protective_stop("BTCUSDT", "sell", 1.0, 1.0) is None
