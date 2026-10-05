"""Tests for cryptobot.data.ingestion."""

from __future__ import annotations

import types
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from cryptobot.core.events import OrderSide
from cryptobot.data.ingestion import (
    OHLCV,
    BinanceDataIngestion,
    DataIngestionManager,
    DataQualityValidator,
    DataSourceConfig,
    FundingRateData,
    FundingRateTracker,
    OrderBookLevel,
    OrderBookReconstructor,
    OrderBookSnapshot,
    Tick,
    TradeData,
    get_ingestion_manager,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _ohlcv(**overrides) -> OHLCV:
    base = dict(
        symbol="BTCUSDT", timeframe="1m", open_time=_now() - timedelta(minutes=5),
        close_time=_now(), open=Decimal("100"), high=Decimal("101"),
        low=Decimal("99"), close=Decimal("100.5"), volume=Decimal("10"),
        trades=5, is_closed=True,
    )
    base.update(overrides)
    return OHLCV(**base)


def _trade(**overrides) -> TradeData:
    base = dict(
        symbol="BTCUSDT", trade_id="t1", timestamp=_now() - timedelta(seconds=1),
        price=Decimal("100"), quantity=Decimal("1"), side=OrderSide.BUY,
        is_maker=False,
    )
    base.update(overrides)
    return TradeData(**base)


def _rate(**overrides) -> FundingRateData:
    base = dict(
        symbol="BTCUSDT", timestamp=_now() - timedelta(hours=1),
        funding_rate=Decimal("0.0001"), mark_price=Decimal("100"),
        index_price=Decimal("99.99"), next_funding_time=_now() + timedelta(hours=7),
    )
    base.update(overrides)
    return FundingRateData(**base)


def _cfg() -> DataSourceConfig:
    return DataSourceConfig(
        name="binance_test",
        venue="binance",
        symbols=["BTCUSDT"],
        timeframes=["1m"],
        base_url="https://api.binance.com",
        ws_url="wss://stream.binance.com:9443",
    )


# --- OrderBookReconstructor ---------------------------------------------------


def test_orderbook_level_creation():
    level = OrderBookLevel(price=Decimal("100"), quantity=Decimal("2"))
    assert level.price == Decimal("100")
    assert level.quantity == Decimal("2")


@pytest.mark.asyncio
async def test_reconstructor_apply_snapshot():
    ob = OrderBookReconstructor("BTCUSDT", max_depth=3)
    bids = [OrderBookLevel(Decimal("100"), Decimal("1")),
            OrderBookLevel(Decimal("99"), Decimal("2"))]
    asks = [OrderBookLevel(Decimal("101"), Decimal("1"))]
    await ob.apply_snapshot(bids, asks, update_id=10)
    assert ob.last_update_id == 10
    assert ob.get_best_bid().price == Decimal("100")
    assert ob.get_best_ask().price == Decimal("101")
    snap = ob.get_snapshot()
    assert isinstance(snap, OrderBookSnapshot)
    assert snap.sequence == 10
    assert snap.spread == Decimal("1")
    assert snap.mid_price == Decimal("100.5")


@pytest.mark.asyncio
async def test_reconstructor_apply_update_success():
    ob = OrderBookReconstructor("BTCUSDT")
    await ob.apply_snapshot([OrderBookLevel(Decimal("100"), Decimal("1"))], [], 5)
    ok = await ob.apply_update(
        [OrderBookLevel(Decimal("100"), Decimal("0"))], [OrderBookLevel(Decimal("101"), Decimal("2"))], 6
    )
    assert ok is True
    assert ob.get_best_bid() is None
    assert ob.get_best_ask().price == Decimal("101")


@pytest.mark.asyncio
async def test_reconstructor_gap_detected():
    ob = OrderBookReconstructor("BTCUSDT")
    await ob.apply_snapshot([], [], update_id=5)
    ok = await ob.apply_update([], [], update_id=10)
    assert ok is False
    assert ob.last_update_id == 5


@pytest.mark.asyncio
async def test_reconstructor_trims_to_max_depth():
    ob = OrderBookReconstructor("BTCUSDT", max_depth=2)
    await ob.apply_snapshot(
        [OrderBookLevel(Decimal(i), Decimal("1")) for i in range(95, 100)],
        [OrderBookLevel(Decimal(i), Decimal("1")) for i in range(100, 105)],
        update_id=1,
    )
    assert len(ob.bids) == 2
    assert len(ob.asks) == 2
    assert ob.get_best_bid().price == Decimal("99")
    assert ob.get_best_ask().price == Decimal("100")


@pytest.mark.asyncio
async def test_reconstructor_best_bid_ask_empty():
    ob = OrderBookReconstructor("BTCUSDT")
    assert ob.get_best_bid() is None
    assert ob.get_best_ask() is None
    snap = ob.get_snapshot()
    assert snap.best_bid is None
    assert snap.spread == Decimal("0")


# --- FundingRateTracker --------------------------------------------------------


@pytest.mark.asyncio
async def test_funding_tracker_add_and_get_latest():
    tracker = FundingRateTracker()
    await tracker.add_rate(_rate(funding_rate=Decimal("0.0001")))
    await tracker.add_rate(_rate(funding_rate=Decimal("0.0002")))
    latest = await tracker.get_latest("BTCUSDT")
    assert latest.funding_rate == Decimal("0.0002")
    assert await tracker.get_latest("NOPE") is None


@pytest.mark.asyncio
async def test_funding_tracker_history_since_and_limit():
    tracker = FundingRateTracker()
    base = _now() - timedelta(hours=10)
    for i in range(5):
        await tracker.add_rate(_rate(timestamp=base + timedelta(hours=i), funding_rate=Decimal(i) / 10000))
    hist = await tracker.get_history("BTCUSDT", since=base + timedelta(hours=2), limit=10)
    assert len(hist) == 3
    limited = await tracker.get_history("BTCUSDT", limit=2)
    assert len(limited) == 2
    assert await tracker.get_history("NOPE") == []


@pytest.mark.asyncio
async def test_funding_tracker_estimate():
    tracker = FundingRateTracker()
    assert await tracker.get_funding_estimate("BTCUSDT") is None
    for i in range(3):
        await tracker.add_rate(_rate(funding_rate=Decimal("0.0001") * (i + 1)))
    est = await tracker.get_funding_estimate("BTCUSDT")
    assert est is not None and est > 0


@pytest.mark.asyncio
async def test_funding_tracker_trims_history():
    tracker = FundingRateTracker()
    tracker.max_history = 3
    for i in range(6):
        await tracker.add_rate(_rate(funding_rate=Decimal(i)))
    assert len(await tracker.get_history("BTCUSDT", limit=100)) == 3


# --- DataQualityValidator --------------------------------------------------------


def test_validate_trade_ok():
    v = DataQualityValidator()
    valid, issues = v.validate_trade(_trade())
    assert valid is True
    assert issues == []


def test_validate_trade_bad_price_quantity():
    v = DataQualityValidator()
    valid, issues = v.validate_trade(_trade(price=Decimal("-1"), quantity=Decimal("0")))
    assert valid is False
    assert any("Price" in i for i in issues)
    assert any("Quantity" in i for i in issues)


def test_validate_trade_future_timestamp():
    v = DataQualityValidator()
    valid, issues = v.validate_trade(_trade(timestamp=_now() + timedelta(hours=1)))
    assert valid is False
    assert any("future" in i.lower() for i in issues)


def test_validate_trade_price_outlier():
    v = DataQualityValidator()
    for i in range(12):
        price = Decimal("99") if i % 2 == 0 else Decimal("101")
        v.add_trade(_trade(price=price, trade_id=f"p{i}"))
    valid, issues = v.validate_trade(_trade(trade_id="outlier", price=Decimal("500")))
    assert valid is False
    assert any("z-score" in i for i in issues)


def test_validate_ohlcv_ok_with_price_history():
    v = DataQualityValidator()
    v.add_ohlcv(_ohlcv(open_time=_now() - timedelta(minutes=10)))
    valid, issues = v.validate_ohlcv(_ohlcv(open_time=_now() - timedelta(minutes=5)))
    assert valid is True
    assert issues == []


def test_validate_ohlcv_high_below_low():
    v = DataQualityValidator()
    valid, issues = v.validate_ohlcv(_ohlcv(high=Decimal("98"), low=Decimal("99")))
    assert valid is False
    assert any("High < Low" in i for i in issues)


def test_validate_ohlcv_high_above_close():
    v = DataQualityValidator()
    valid, issues = v.validate_ohlcv(_ohlcv(high=Decimal("98"), close=Decimal("99")))
    assert valid is False
    assert any("High < Open/Close" in i for i in issues)


def test_validate_ohlcv_low_below_open():
    v = DataQualityValidator()
    valid, issues = v.validate_ohlcv(_ohlcv(low=Decimal("101"), open=Decimal("100")))
    assert valid is False
    assert any("Low > Open/Close" in i for i in issues)


def test_validate_ohlcv_negative_price():
    v = DataQualityValidator()
    valid, issues = v.validate_ohlcv(_ohlcv(open=Decimal("-1")))
    assert any("positive" in i for i in issues)


def test_validate_ohlcv_negative_volume():
    v = DataQualityValidator()
    valid, issues = v.validate_ohlcv(_ohlcv(volume=Decimal("-1")))
    assert any("negative" in i.lower() for i in issues)


def test_validate_ohlcv_non_monotonic_timestamp():
    v = DataQualityValidator()
    first = _ohlcv(open_time=_now() - timedelta(minutes=2))
    second = _ohlcv(open_time=_now() - timedelta(minutes=1))
    v.add_ohlcv(second)
    valid, issues = v.validate_ohlcv(first)
    assert any("monotonic" in i.lower() for i in issues)


def test_validator_add_trade_initializes_history():
    v = DataQualityValidator()
    v.add_trade(_trade())
    assert "BTCUSDT" in v.price_history
    assert "BTCUSDT" in v.volume_history


# --- BinanceDataIngestion parsing -------------------------------------------


def test_binance_ingestion_init():
    bi = BinanceDataIngestion(_cfg())
    assert bi.config.name == "binance_test"
    assert bi._running is False
    assert bi.funding_tracker is not None
    assert bi.quality_validator is not None
    assert bi.order_books == {}


@pytest.mark.asyncio
async def test_parse_ws_kline():
    bi = BinanceDataIngestion(_cfg())
    msg = {
        "e": "kline",
        "s": "BTCUSDT",
        "k": {"i": "1m", "t": 1704067200000, "T": 1704067260000,
              "o": "100", "h": "101", "l": "99", "c": "100.5",
              "v": "10", "n": 5, "x": True},
    }
    event = await bi._parse_ws_message(msg, "BTCUSDT", "1m")
    assert event is not None
    assert event.symbol == "BTCUSDT"
    assert event.close_price == Decimal("100.5")
    assert event.is_closed is True


@pytest.mark.asyncio
async def test_parse_ws_trade():
    bi = BinanceDataIngestion(_cfg())
    msg = {"e": "trade", "s": "BTCUSDT", "t": "123", "p": "100.5",
           "q": "0.5", "m": False, "T": 1704067200000}
    event = await bi._parse_ws_message(msg, "BTCUSDT", "1m")
    assert event is not None
    assert event.trade_id == "123"
    assert event.side == OrderSide.BUY


@pytest.mark.asyncio
async def test_parse_ws_book_ticker():
    bi = BinanceDataIngestion(_cfg())
    msg = {"s": "BTCUSDT", "b": "100", "a": "101", "B": "1", "A": "2"}
    event = await bi._parse_ws_message(msg, "BTCUSDT", "1m")
    assert event is not None
    assert event.bid == Decimal("100")
    assert event.ask == Decimal("101")


@pytest.mark.asyncio
async def test_parse_ws_mark_price_tracks_funding():
    bi = BinanceDataIngestion(_cfg())
    msg = {"e": "markPrice", "s": "BTCUSDT", "r": "0.0001", "p": "100",
           "i": "99.99", "b": "99.9", "a": "100.1", "B": "1", "A": "1", "T": 1704067200000}
    event = await bi._parse_ws_message(msg, "BTCUSDT", "1m")
    assert event is not None
    hist = await bi.funding_tracker.get_history("BTCUSDT", limit=10)
    assert len(hist) == 1
    assert hist[0].funding_rate == Decimal("0.0001")


@pytest.mark.asyncio
async def test_parse_ws_depth_update():
    bi = BinanceDataIngestion(_cfg())
    bi.order_books["BTCUSDT"] = OrderBookReconstructor("BTCUSDT")
    await bi.order_books["BTCUSDT"].apply_snapshot(
        [OrderBookLevel(Decimal("100"), Decimal("2"))],
        [OrderBookLevel(Decimal("101"), Decimal("2"))],
        update_id=5,
    )
    msg = {"e": "depthUpdate", "u": 6, "s": "BTCUSDT",
           "b": [["99", "1"]], "a": [["101", "0"]]}
    event = await bi._parse_ws_message(msg, "BTCUSDT", "1m")
    assert event is not None
    assert event.bid == Decimal("100")
    assert event.ask == Decimal("0")


@pytest.mark.asyncio
async def test_parse_ws_unknown_type_returns_none():
    bi = BinanceDataIngestion(_cfg())
    assert await bi._parse_ws_message({"e": "unknown", "s": "BTCUSDT"}, "BTCUSDT", "1m") is None


@pytest.mark.asyncio
async def test_fetch_funding_history_and_snapshot():
    bi = BinanceDataIngestion(_cfg())
    await bi.funding_tracker.add_rate(_rate())
    hist = await bi.fetch_funding_history("BTCUSDT", _now() - timedelta(days=1), _now())
    assert len(hist) == 1
    assert await bi.get_order_book_snapshot("NOPE") is None


@pytest.mark.asyncio
async def test_get_funding_estimate_wraps_tracker():
    bi = BinanceDataIngestion(_cfg())
    assert await bi.get_funding_estimate("BTCUSDT") is None
    await bi.funding_tracker.add_rate(_rate(funding_rate=Decimal("0.0001")))
    assert await bi.get_funding_estimate("BTCUSDT") == Decimal("0.0001")


# --- fetch_historical (mocked HTTP) ---------------------------------------------


@pytest.mark.asyncio
async def test_fetch_historical_parses_klines(monkeypatch):
    bi = BinanceDataIngestion(_cfg())
    bi._session = types.SimpleNamespace(closed=False)  # pretend connected

    class _FakeResp:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def json(self):
            return [[1704067200000, "100", "101", "99", "100.5", "10",
                     1704067260000, "500000", 5, "0", "0", "0"]]

    calls = {"n": 0}

    async def fake_get(*a, **kw):
        calls["n"] += 1
        if calls["n"] > 1:
            return []
        return await _FakeResp().json()

    monkeypatch.setattr(bi, "_rate_limited_get", fake_get)
    start = datetime.fromtimestamp(1704067200, tz=UTC)
    end = start + timedelta(hours=1)
    data = await bi.fetch_historical("BTCUSDT", "1m", start, end)
    assert len(data) == 1
    assert data[0]["symbol"] == "BTCUSDT"
    assert data[0]["open_price"] == Decimal("100")
    assert data[0]["interval"] == "1m"


@pytest.mark.asyncio
async def test_fetch_historical_empty_stops(monkeypatch):
    bi = BinanceDataIngestion(_cfg())
    bi._session = types.SimpleNamespace(closed=False)

    async def fake_get(*a, **kw):
        return []

    monkeypatch.setattr(bi, "_rate_limited_get", fake_get)
    start = datetime.fromtimestamp(1704067200, tz=UTC)
    data = await bi.fetch_historical("BTCUSDT", "1m", start, start + timedelta(hours=1))
    assert data == []


# --- DataIngestionManager --------------------------------------------------------


def test_ingestion_manager_register_and_enabled_filter():
    mgr = DataIngestionManager()
    on = BinanceDataIngestion(_cfg())
    off = BinanceDataIngestion(DataSourceConfig(name="off", venue="binance",
                                                symbols=[], timeframes=[], enabled=False))
    mgr.register_source(on)
    mgr.register_source(off)
    assert on.config.name in mgr.sources
    assert off.config.name in mgr.sources


@pytest.mark.asyncio
async def test_manager_start_all_respects_enabled(monkeypatch):
    mgr = DataIngestionManager()
    started = []

    async def fake_start(self):
        started.append(self.config.name)

    on = BinanceDataIngestion(_cfg())
    off = BinanceDataIngestion(DataSourceConfig(name="disabled", venue="binance",
                                                symbols=[], timeframes=[], enabled=False))
    monkeypatch.setattr(on, "start", lambda: fake_start(on))
    monkeypatch.setattr(off, "start", lambda: fake_start(off))
    mgr.register_source(on)
    mgr.register_source(off)
    await mgr.start_all()
    assert started == [on.config.name]


@pytest.mark.asyncio
async def test_manager_stop_all(monkeypatch):
    mgr = DataIngestionManager()
    stopped = []

    async def fake_stop(self):
        stopped.append(self.config.name)

    src = BinanceDataIngestion(_cfg())
    monkeypatch.setattr(src, "stop", lambda: fake_stop(src))
    mgr.register_source(src)
    await mgr.stop_all()
    assert stopped == [src.config.name]


@pytest.mark.asyncio
async def test_fetch_all_historical_bad_venue(monkeypatch):
    mgr = DataIngestionManager()
    with pytest.raises(ValueError, match="nope"):
        await mgr.fetch_all_historical(["BTCUSDT"], ["1m"], _now(), _now(), venue="nope")


def test_get_ingestion_manager_singleton(monkeypatch):
    import cryptobot.data.ingestion as ing_mod
    monkeypatch.setattr(ing_mod, "_ingestion_manager", None)
    first = get_ingestion_manager()
    second = get_ingestion_manager()
    assert first is second


# --- Tick helpers -----------------------------------------------------------------


def test_tick_spread_and_mid():
    t = Tick(symbol="BTCUSDT", timestamp=_now(), bid=Decimal("100"), ask=Decimal("102"), last=Decimal("101"))
    assert t.spread == Decimal("2")
    assert t.mid == Decimal("101")


# --- original data-less smoke tests ---------------------------------------------


def test_ohlcv_to_dict():
    o = OHLCV(
        symbol="BTCUSDT",
        timeframe="1m",
        open_time=datetime(2024, 1, 1, tzinfo=UTC),
        close_time=datetime(2024, 1, 1, tzinfo=UTC),
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("95"),
        close=Decimal("105"),
        volume=Decimal("10"),
    )
    d = o.to_dict()
    assert d["symbol"] == "BTCUSDT"
    assert d["open"] == "100"


def test_data_source_config_defaults():
    cfg = DataSourceConfig(
        name="binance",
        venue="binance",
        symbols=["BTCUSDT"],
        timeframes=["1m"],
    )
    assert cfg.name == "binance"
    assert cfg.enabled is True
    assert cfg.rate_limit == 1200


@pytest.mark.asyncio
async def test_binance_data_ingestion_start_stop():
    ing = BinanceDataIngestion(_cfg())
    await ing.start()
    assert ing._running is True
    await ing.stop()
    assert ing._running is False


def test_data_ingestion_abstract_methods():
    import inspect

    from cryptobot.data.ingestion import DataIngestion
    assert inspect.isabstract(DataIngestion)
    for method in ["start", "stop", "fetch_historical", "subscribe_realtime"]:
        assert hasattr(DataIngestion, method)
