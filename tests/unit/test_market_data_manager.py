"""Tests for cryptobot.market_data.manager.

No network access; tested with hand-built Events and a mock aiohttp
client. The cache layer can run with `redis=None` to skip the network
deps entirely.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from cryptobot.core.events import (
    EventType,
    OrderBookEvent,
    TickerEvent,
)
from cryptobot.market_data.manager import (
    BinanceWSClient,
    MarketDataCache,
    MarketDataManager,
)

# --- TickerEvent / OrderBookEvent helpers ---------------------------------


def _ticker(symbol: str = "BTCUSDT", price: str = "100"):
    return TickerEvent(
        symbol=symbol,
        price=Decimal(price),
        bid=Decimal("99.5"),
        ask=Decimal("100.5"),
        bid_qty=Decimal("1"),
        ask_qty=Decimal("1"),
        volume_24h=Decimal("1000"),
        timestamp=datetime.now(UTC),
        source="binance_ws",
    )


def _book(symbol: str = "BTCUSDT"):
    return OrderBookEvent(
        symbol=symbol,
        bids=[(Decimal("99.5"), Decimal("1")), (Decimal("99"), Decimal("2"))],
        asks=[(Decimal("100.5"), Decimal("1.5")), (Decimal("101"), Decimal("2"))],
        sequence=1,
        timestamp=datetime.now(UTC),
        source="binance_ws",
    )


# --- BinanceWSClient URL building + reconnect -----------------------------


def test_binance_wsclient_build_streams_includes_required_channels():

    ws = BinanceWSClient()
    ws._symbols = ["BTCUSDT", "ETHUSDT"]
    ws._timeframes = ["1m"]
    streams = ws._build_streams()
    assert any("btcusdt@ticker" in s for s in streams)
    assert any("ethusdt@trade" in s for s in streams)
    assert any("btcusdt@kline_1m" in s for s in streams)


def test_binance_wsclient_message_handling_dispatches_to_correct_handler(monkeypatch):
    ws = BinanceWSClient()
    captured: dict[str, int] = {}

    async def _tick(p): captured["tick"] = captured.get("tick", 0) + 1
    async def _book(p): captured["book"] = captured.get("book", 0) + 1
    async def _trade(p): captured["trade"] = captured.get("trade", 0) + 1
    async def _kline(p): captured["kline"] = captured.get("kline", 0) + 1
    async def _mark(p): captured["mark"] = captured.get("mark", 0) + 1

    ws._handle_ticker = _tick
    ws._handle_orderbook = _book
    ws._handle_trade = _trade
    ws._handle_kline = _kline
    ws._handle_mark_price = _mark

    import asyncio

    cases = [
        ('{"stream":"btcusdt@ticker","data":{"s":"BTCUSDT"}}', "tick"),
        ('{"stream":"btcusdt@depth20@100ms","data":{"s":"BTCUSDT"}}', "book"),
        ('{"stream":"btcusdt@trade","data":{"s":"BTCUSDT"}}', "trade"),
        ('{"stream":"btcusdt@kline_1m","data":{"k":{"s":"BTCUSDT"}}}', "kline"),
        ('{"stream":"btcusdt@markPrice@1s","data":{"s":"BTCUSDT","r":"0.001","p":"100","i":"100","T":0}}', "mark"),
        ("not-json", None),
    ]
    for raw, expected in cases:
        asyncio.run(ws._handle_message(raw))
    assert captured == {"tick": 1, "book": 1, "trade": 1, "kline": 1, "mark": 1}


def test_binance_wsclient_subscribe_appends_callback():
    ws = BinanceWSClient()
    seen: list[str] = []
    ws.subscribe(EventType.TICKER, lambda e: seen.append(e))
    ws.callbacks[EventType.TICKER.value].append(lambda e: seen.append("late"))
    assert len(ws.callbacks[EventType.TICKER.value]) == 2


# --- MarketDataCache -----------------------------------------------------


def test_market_data_cache_local_roundtrip_no_redis():
    import asyncio

    cache = MarketDataCache()
    ticker = _ticker()

    async def run():
        await cache.set_ticker(ticker)
        got = await cache.get_ticker("BTCUSDT")
        return got

    result = asyncio.run(run())
    assert result is not None
    assert result["payload"]["symbol"] == "BTCUSDT"


def test_market_data_cache_orderbook_roundtrip_no_redis():
    import asyncio

    cache = MarketDataCache()
    book = _book()

    async def run():
        await cache.set_orderbook(book)
        return await cache.get_orderbook("BTCUSDT")

    result = asyncio.run(run())
    assert result is not None
    assert result["payload"]["sequence"] == 1


def test_market_data_cache_returns_none_on_miss():
    import asyncio

    cache = MarketDataCache()

    async def run():
        return await cache.get_ticker("NOPE")

    assert asyncio.run(run()) is None


# --- MarketDataManager fallback path ------------------------------------


def test_market_data_manager_get_mid_price_orderbook_first(monkeypatch):
    mgr = MarketDataManager()
    mgr.cache = MarketDataCache()
    _book()
    mgr.cache.local_cache["orderbook:BTCUSDT"] = {
        "symbol": "BTCUSDT",
        "bids": [[99.5, 1.0]],
        "asks": [[100.5, 1.0]],
        "sequence": 1,
        "timestamp": datetime.now(UTC).isoformat(),
        "source": "binance_ws",
    }
    mid = mgr.get_mid_price("BTCUSDT")
    assert mid == Decimal("100")


def test_market_data_manager_get_mid_price_zero_when_no_data():
    mgr = MarketDataManager()
    mgr.cache = MarketDataCache()
    assert mgr.get_mid_price("NOPE") == Decimal("0")


# --- Real payload parsers ---------------------------------------------------


def test_handle_ticker_parses_payload():
    import asyncio

    ws = BinanceWSClient()
    captured = []

    async def _emit(etype, event):
        captured.append((etype, event))

    ws._emit = _emit
    data = {
        "s": "BTCUSDT", "c": "50000.5", "b": "49999", "a": "50001",
        "B": "1.5", "A": "2.5", "h": "51000", "l": "49000",
        "v": "12345.6", "P": "1.23",
    }
    asyncio.run(ws._handle_ticker(data))
    assert captured
    etype, event = captured[0]
    assert etype == EventType.TICKER
    assert event.price == Decimal("50000.5")
    assert event.bid == Decimal("49999")
    assert event.change_24h == 1.23


def test_handle_orderbook_parses_payload():
    import asyncio

    ws = BinanceWSClient()
    captured = []

    async def _emit(etype, event):
        captured.append((etype, event))

    ws._emit = _emit
    data = {
        "s": "BTCUSDT", "u": 42,
        "b": [["99.5", "1.0"], ["99", "2.0"]],
        "a": [["100.5", "1.5"]],
    }
    asyncio.run(ws._handle_orderbook(data))
    etype, event = captured[0]
    assert etype == EventType.ORDERBOOK
    assert event.bids[0] == (Decimal("99.5"), Decimal("1.0"))
    assert event.asks[0] == (Decimal("100.5"), Decimal("1.5"))
    assert event.sequence == 42


def test_handle_trade_parses_payload():
    import asyncio

    from cryptobot.core.events import OrderSide

    ws = BinanceWSClient()
    captured = []

    async def _emit(etype, event):
        captured.append((etype, event))

    ws._emit = _emit
    data = {"s": "BTCUSDT", "t": 12345, "p": "50000", "q": "0.5", "m": True}
    asyncio.run(ws._handle_trade(data))
    etype, event = captured[0]
    assert etype == EventType.TRADE
    assert event.trade_id == "12345"
    assert event.side == OrderSide.SELL
    assert event.is_maker is True


def test_handle_trade_buy_side():
    import asyncio

    from cryptobot.core.events import OrderSide

    ws = BinanceWSClient()
    captured = []

    async def _emit(etype, event):
        captured.append((etype, event))

    ws._emit = _emit
    data = {"s": "BTCUSDT", "t": 1, "p": "1", "q": "1", "m": False}
    asyncio.run(ws._handle_trade(data))
    assert captured[0][1].side == OrderSide.BUY


def test_handle_kline_parses_payload():
    import asyncio

    ws = BinanceWSClient()
    captured = []

    async def _emit(etype, event):
        captured.append((etype, event))

    ws._emit = _emit
    data = {"k": {"s": "BTCUSDT", "i": "1m", "t": 1704067200000, "T": 1704067260000,
                  "o": "100", "h": "101", "l": "99", "c": "100.5", "v": "10",
                  "n": 5, "x": True}}
    asyncio.run(ws._handle_kline(data))
    etype, event = captured[0]
    assert etype == EventType.KLINE
    assert event.symbol == "BTCUSDT"
    assert event.interval == "1m"
    assert event.open_time == datetime.fromtimestamp(1704067200000 / 1000)
    assert event.close_price == Decimal("100.5")
    assert event.trades == 5
    assert event.is_closed is True


def test_handle_mark_price_parses_payload():
    import asyncio

    ws = BinanceWSClient()
    captured = []

    async def _emit(etype, event):
        captured.append((etype, event))

    ws._emit = _emit
    data = {"s": "BTCUSDT", "r": "0.0001", "p": "50000", "i": "49999.5", "T": 1704067260000}
    asyncio.run(ws._handle_mark_price(data))
    etype, event = captured[0]
    assert etype == EventType.FUNDING_RATE
    assert event.funding_rate == 0.0001
    assert event.mark_price == Decimal("50000")
    assert event.index_price == Decimal("49999.5")


def test_emit_supports_sync_callbacks():
    import asyncio

    ws = BinanceWSClient()
    seen = []
    ws.subscribe(EventType.TICKER, lambda e: seen.append(e))
    ws.subscribe(EventType.TICKER, lambda e: (_ for _ in ()).throw(RuntimeError("boom")))
    asyncio.run(ws._emit(EventType.TICKER, _ticker()))
    assert len(seen) == 1


def test_emit_async_callbacks_run():
    import asyncio

    ws = BinanceWSClient()
    seen = []

    async def _cb(event):
        seen.append(event.symbol)

    ws.subscribe(EventType.TICKER, _cb)
    asyncio.run(ws._emit(EventType.TICKER, _ticker("ETHUSDT")))
    assert seen == ["ETHUSDT"]


def test_emit_async_callback_error_logged():
    import asyncio

    ws = BinanceWSClient()

    async def _bad(event):
        raise RuntimeError("callback failed")

    ws.subscribe(EventType.TICKER, _bad)
    asyncio.run(ws._emit(EventType.TICKER, _ticker()))


# --- Cache: kline + funding + redis path ------------------------------------


def test_market_data_cache_kline_roundtrip():
    import asyncio

    from cryptobot.core.events import KlineEvent

    cache = MarketDataCache()
    event = KlineEvent(
        symbol="BTCUSDT", interval="1m",
        open_time=datetime(2024, 1, 1, tzinfo=UTC),
        close_time=datetime(2024, 1, 1, 0, 5, tzinfo=UTC),
        open_price=Decimal("100"), high_price=Decimal("101"),
        low_price=Decimal("99"), close_price=Decimal("100.5"),
        volume=Decimal("10"), trades=5, is_closed=True, source="binance_ws",
    )

    async def run():
        await cache.set_kline(event)
        assert await cache.get_klines("BTCUSDT", "1m") != []
        assert await cache.get_klines("NOPE", "1m") == []

    asyncio.run(run())


def test_market_data_cache_funding_roundtrip():
    import asyncio

    from cryptobot.core.events import FundingRateEvent

    cache = MarketDataCache()
    event = FundingRateEvent(
        symbol="BTCUSDT", funding_rate=0.0001,
        mark_price=Decimal("50000"), index_price=Decimal("49999"),
        next_funding_time=datetime(2024, 1, 1, 8, tzinfo=UTC),
        source="binance_ws",
    )

    async def run():
        await cache.set_funding_rate(event)
        got = await cache.get_funding_rate("BTCUSDT")
        assert got is not None
        assert got["payload"]["symbol"] == "BTCUSDT"
        assert await cache.get_funding_rate("NOPE") is None

    asyncio.run(run())


def test_market_data_cache_redis_roundtrip(monkeypatch):
    import asyncio


    class _FakeRedis:
        def __init__(self):
            self.store = {}
            self.closed = False

        async def setex(self, key, ttl, value):
            self.store[key] = value

        async def get(self, key):
            return self.store.get(key)

        async def close(self):
            self.closed = True

    fake = _FakeRedis()
    monkeypatch.setattr("cryptobot.market_data.manager.redis.Redis", lambda **kw: fake)

    cache = MarketDataCache()

    async def run():
        await cache.start()
        assert cache.redis is fake
        await cache.set_ticker(_ticker("SOLUSDT"))
        # bypass local cache to force redis read
        cache.local_cache.clear()
        got = await cache.get_ticker("SOLUSDT")
        assert got is not None
        assert got["payload"]["symbol"] == "SOLUSDT"
        # orderbook redis path
        await cache.set_orderbook(_book("SOLUSDT"))
        cache.local_cache.clear()
        assert (await cache.get_orderbook("SOLUSDT")) is not None
        # funding redis path
        from cryptobot.core.events import FundingRateEvent
        ev = FundingRateEvent(
            symbol="SOLUSDT", funding_rate=0.0001, mark_price=Decimal("1"),
            index_price=Decimal("1"),
            next_funding_time=datetime(2024, 1, 1, 8, tzinfo=UTC),
            source="binance_ws",
        )
        await cache.set_funding_rate(ev)
        cache.local_cache.clear()
        assert (await cache.get_funding_rate("SOLUSDT")) is not None
        await cache.stop()
        assert fake.closed is True

    asyncio.run(run())


# --- MarketDataManager flow --------------------------------------------------


def test_market_data_manager_get_ticker_and_orderbook(monkeypatch):
    mgr = MarketDataManager()
    mgr.cache = MarketDataCache()
    mgr.cache.local_cache["ticker:BTCUSDT"] = _ticker().to_dict()
    mgr.cache.local_cache["orderbook:BTCUSDT"] = _book().to_dict()

    t = mgr.get_ticker("BTCUSDT")
    assert t is not None
    assert t.symbol == "BTCUSDT"
    ob = mgr.get_orderbook("BTCUSDT")
    assert ob is not None
    assert ob.sequence == 1
    assert mgr.get_ticker("NOPE") is None
    assert mgr.get_orderbook("NOPE") is None


def test_market_data_manager_get_mid_price_from_ticker_fallback():
    mgr = MarketDataManager()
    mgr.cache = MarketDataCache()
    mgr.cache.local_cache["ticker:BTCUSDT"] = _ticker(price="123.45").to_dict()
    assert mgr.get_mid_price("BTCUSDT") == Decimal("123.45")


def test_market_data_manager_handlers_emit_and_cache(monkeypatch):
    import asyncio

    from cryptobot.core.events import (
        FundingRateEvent,
        KlineEvent,
        OrderSide,
        TradeEvent,
    )

    mgr = MarketDataManager()
    mgr.cache = MarketDataCache()
    emitted = []

    async def _cb(event):
        emitted.append(event)

    for etype in (EventType.TICKER, EventType.ORDERBOOK, EventType.TRADE,
                  EventType.KLINE, EventType.FUNDING_RATE):
        mgr.subscribe(etype, _cb)

    now = datetime.now(UTC)
    kline = KlineEvent(
        symbol="BTCUSDT", interval="1m", open_time=now, close_time=now,
        open_price=Decimal("100"), high_price=Decimal("101"),
        low_price=Decimal("99"), close_price=Decimal("100.5"),
        volume=Decimal("10"), trades=5, is_closed=True, source="binance_ws",
    )
    funding = FundingRateEvent(
        symbol="BTCUSDT", funding_rate=0.0001,
        mark_price=Decimal("50000"), index_price=Decimal("49999"),
        next_funding_time=now, source="binance_ws",
    )
    trade = TradeEvent(
        symbol="BTCUSDT", trade_id="1", price=Decimal("100"),
        quantity=Decimal("1"), side=OrderSide.BUY, is_maker=False,
        source="binance_ws",
    )

    async def run():
        await mgr._on_ticker(_ticker("BTCUSDT"))
        await mgr._on_orderbook(_book("BTCUSDT"))
        await mgr._on_trade(trade)
        await mgr._on_kline(kline)
        await mgr._on_funding(funding)

    asyncio.run(run())
    assert len(emitted) == 5
    assert mgr.cache.local_cache.get("ticker:BTCUSDT") is not None
    assert mgr.cache.local_cache.get("orderbook:BTCUSDT") is not None
    assert mgr.cache.local_cache.get("kline:BTCUSDT:1m") is not None
    assert mgr.cache.local_cache.get("funding:BTCUSDT") is not None


def test_market_data_manager_subscribe_stores_callback():
    mgr = MarketDataManager()
    cb = lambda e: None  # noqa: E731
    mgr.subscribe(EventType.TRADE, cb)
    assert mgr._callbacks[EventType.TRADE] == [cb]


def test_market_data_manager_emit_sync_callback():
    import asyncio

    mgr = MarketDataManager()
    seen = []
    mgr.subscribe(EventType.TICKER, lambda e: seen.append(e.symbol))
    asyncio.run(mgr._emit(EventType.TICKER, _ticker("BTCUSDT")))
    assert seen == ["BTCUSDT"]
