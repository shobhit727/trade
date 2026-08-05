from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from cryptobot.utils.types import (
    Candle,
    OrderBook,
    OrderBookLevel,
    Trade,
)

# --- Candle --------------------------------------------------------------

def test_candle_from_dict():
    data = {
        "timestamp": "2024-01-01T00:00:00+00:00",
        "open": "100",
        "high": "110",
        "low": "95",
        "close": "105",
        "volume": "10",
        "trades": 5,
    }
    c = Candle.from_dict(data)
    assert c.open == Decimal("100")
    assert c.high == Decimal("110")
    assert c.body == Decimal("5")
    assert c.trades == 5


def test_candle_to_dict():
    ts = datetime(2024, 1, 1, tzinfo=UTC)
    c = Candle(timestamp=ts, open=Decimal("1"), high=Decimal("2"),
               low=Decimal("0.5"), close=Decimal("1.5"), volume=Decimal("100"))
    d = c.to_dict()
    assert d["timestamp"] == ts.isoformat()
    assert d["open"] == "1"
    assert d["trades"] == 0


def test_candle_bullish_properties():
    c = Candle(
        timestamp=datetime.now(UTC),
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal("105"),
        volume=Decimal("10"),
    )
    assert c.body == Decimal("5")
    assert c.upper_shadow == Decimal("5")
    assert c.lower_shadow == Decimal("10")
    assert c.is_bullish is True
    assert c.is_bearish is False


def test_candle_bearish():
    c = Candle(
        timestamp=datetime.now(UTC),
        open=Decimal("100"),
        high=Decimal("105"),
        low=Decimal("90"),
        close=Decimal("95"),
        volume=Decimal("10"),
    )
    assert c.is_bullish is False
    assert c.is_bearish is True
    assert c.upper_shadow == Decimal("5")


# --- OrderBookLevel ------------------------------------------------------

def test_orderbook_level_total():
    level = OrderBookLevel(price=Decimal("100"), quantity=Decimal("5"))
    assert level.total == Decimal("500")


def test_orderbook_level_from_tuple():
    level = OrderBookLevel.from_tuple((Decimal("100"), Decimal("2")))
    assert level.price == Decimal("100")
    assert level.quantity == Decimal("2")
    assert level.total == Decimal("200")


def test_orderbook_level_from_tuple_strings():
    level = OrderBookLevel.from_tuple(("99.5", "3"))
    assert level.price == Decimal("99.5")


# --- OrderBook -----------------------------------------------------------

def test_orderbook_empty():
    ts = datetime.now(UTC)
    ob = OrderBook(symbol="ETHUSDT", timestamp=ts)
    assert ob.best_bid is None
    assert ob.best_ask is None
    assert ob.mid_price is None
    assert ob.spread is None
    assert ob.imbalance() is None


def test_orderbook_with_levels():
    ts = datetime.now(UTC)
    bids = [OrderBookLevel(price=Decimal("99"), quantity=Decimal("1"))]
    asks = [OrderBookLevel(price=Decimal("101"), quantity=Decimal("2"))]
    ob = OrderBook(symbol="BTCUSDT", timestamp=ts, bids=bids, asks=asks)
    assert ob.best_bid == Decimal("99")
    assert ob.best_ask == Decimal("101")
    assert ob.mid_price == Decimal("100")
    assert ob.spread == Decimal("2")


def test_orderbook_depth():
    ts = datetime.now(UTC)
    bids = [OrderBookLevel(price=Decimal("100"), quantity=Decimal("1"))]
    asks = [OrderBookLevel(price=Decimal("101"), quantity=Decimal("2"))]
    ob = OrderBook(symbol="BTCUSDT", timestamp=ts, bids=bids, asks=asks)
    depth = ob.depth(levels=5)
    assert len(depth["bids"]) == 1
    assert len(depth["asks"]) == 1
    assert depth["bids"][0]["price"] == "100"


def test_orderbook_imbalance():
    ts = datetime.now(UTC)
    bids = [OrderBookLevel(price=Decimal("100"), quantity=Decimal("10"))]
    asks = [OrderBookLevel(price=Decimal("101"), quantity=Decimal("2"))]
    ob = OrderBook(symbol="BTCUSDT", timestamp=ts, bids=bids, asks=asks)
    imb = ob.imbalance()
    assert imb is not None
    assert imb > Decimal("0")


def test_orderbook_imbalance_zero_volume():
    ts = datetime.now(UTC)
    bids = [OrderBookLevel(price=Decimal("100"), quantity=Decimal("0"))]
    asks = [OrderBookLevel(price=Decimal("101"), quantity=Decimal("0"))]
    ob = OrderBook(symbol="BTCUSDT", timestamp=ts, bids=bids, asks=asks)
    assert ob.imbalance() == Decimal("0")


# --- Trade ---------------------------------------------------------------

def test_trade_creation():
    t = Trade(
        symbol="BTCUSDT",
        price=Decimal("100"),
        quantity=Decimal("1"),
        side="buy",
        timestamp=datetime.now(UTC),
    )
    assert t.symbol == "BTCUSDT"
    assert t.value == Decimal("100")


def test_trade_default_trade_id():
    t = Trade(
        symbol="BTCUSDT",
        price=Decimal("100"),
        quantity=Decimal("1"),
        side="sell",
        timestamp=datetime.now(UTC),
    )
    assert t.trade_id == ""
    assert t.is_maker is False


__all__ = []
