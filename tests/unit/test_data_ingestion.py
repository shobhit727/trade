from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from cryptobot.data.ingestion import (
    OHLCV,
    BinanceDataIngestion,
    DataIngestion,
    DataSourceConfig,
    Tick,
    TradeData,
)


def test_ohlcv_creation():
    from datetime import datetime
    o = OHLCV(
        symbol="BTCUSDT",
        timeframe="1m",
        open_time=datetime.now(UTC),
        close_time=datetime.now(UTC),
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("95"),
        close=Decimal("105"),
        volume=Decimal("10"),
    )
    assert o.symbol == "BTCUSDT"
    assert o.is_closed is True


def test_ohlcv_to_dict():
    from datetime import datetime
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


def test_tick_properties():
    t = Tick(
        symbol="BTCUSDT",
        timestamp=datetime.now(UTC),
        bid=Decimal("99"),
        ask=Decimal("101"),
        last=Decimal("100"),
    )
    assert t.spread == Decimal("2")
    assert t.mid == Decimal("100")


def test_trade_data_creation():
    td = TradeData(
        symbol="BTCUSDT",
        trade_id="12345",
        timestamp=datetime.now(UTC),
        price=Decimal("100"),
        quantity=Decimal("1"),
        side="buy",
    )
    assert td.symbol == "BTCUSDT"
    assert td.trade_id == "12345"


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


def test_binance_data_ingestion_init():
    cfg = DataSourceConfig(
        name="binance",
        venue="binance",
        symbols=["BTCUSDT"],
        timeframes=["1m"],
    )
    ing = BinanceDataIngestion(cfg)
    assert ing.config == cfg
    assert ing._running is False


def test_binance_data_ingestion_start_stop():
    import asyncio
    cfg = DataSourceConfig(
        name="binance",
        venue="binance",
        symbols=["BTCUSDT"],
        timeframes=["1m"],
    )
    ing = BinanceDataIngestion(cfg)
    asyncio.run(ing.start())
    assert ing._running is True
    asyncio.run(ing.stop())
    assert ing._running is False


def test_data_ingestion_abstract_methods():
    """Test that DataIngestion is an abstract base class."""
    import inspect
    assert inspect.isabstract(DataIngestion)

    # All required methods should be abstract
    for method in ["start", "stop", "fetch_historical", "subscribe_realtime"]:
        assert hasattr(DataIngestion, method)


__all__ = []
