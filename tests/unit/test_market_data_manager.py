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
    from cryptobot.core.events import EventType

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
        event_id="t1",
        event_type=EventType.TICKER,
        payload={},
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
    assert result["symbol"] == "BTCUSDT"


def test_market_data_cache_orderbook_roundtrip_no_redis():
    import asyncio

    cache = MarketDataCache()
    book = _book()

    async def run():
        await cache.set_orderbook(book)
        return await cache.get_orderbook("BTCUSDT")

    result = asyncio.run(run())
    assert result is not None
    assert result["sequence"] == 1


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
