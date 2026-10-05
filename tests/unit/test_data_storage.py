from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from cryptobot.data.storage import (
    HybridStorage,
    ParquetDataFrameStorage,
    ParquetStorage,
    StorageBackend,
    StorageConfig,
    TimescaleDBStorage,
)


def test_storage_config_defaults():
    cfg = StorageConfig()
    assert cfg.timescaledb_host == "timescaledb"
    assert cfg.timescaledb_port == 5432
    assert cfg.parquet_compression == "zstd"
    assert cfg.batch_size == 1000


def test_storage_backend_is_abstract():
    import inspect
    assert inspect.isabstract(StorageBackend)
    for method in ["initialize", "close", "write_klines", "write_tickers", "write_trades",
                   "write_funding_rates", "read_klines", "read_tickers"]:
        assert hasattr(StorageBackend, method)


def test_timescale_storage_init():
    cfg = StorageConfig()
    ts = TimescaleDBStorage(cfg)
    assert ts.config == cfg
    assert ts.pool is None


def test_parquet_storage_init(tmp_path):
    cfg = StorageConfig(parquet_base_path=str(tmp_path))
    ps = ParquetStorage(cfg)
    assert ps.config == cfg


def test_parquet_dataframe_storage_init(tmp_path):
    pds = ParquetDataFrameStorage(base_path=str(tmp_path))
    assert pds.base_path == tmp_path


def _requires_pyarrow():
    import importlib.util
    if importlib.util.find_spec("pyarrow") is None:
        pytest.skip("pyarrow not available")


def test_parquet_dataframe_storage_store_ohlcv(tmp_path):
    _requires_pyarrow()
    pds = ParquetDataFrameStorage(base_path=str(tmp_path))
    df = pd.DataFrame({
        "symbol": ["BTCUSDT", "BTCUSDT"],
        "open_time": [datetime(2024, 1, 1, tzinfo=UTC),
                      datetime(2024, 1, 2, tzinfo=UTC)],
        "open": [100, 101],
        "high": [105, 106],
        "low": [95, 96],
        "close": [102, 103],
        "volume": [10, 11],
    })
    result = pds.store_ohlcv(df)
    assert result is not None
    assert result.exists()


def test_parquet_dataframe_storage_load_ohlcv(tmp_path):
    _requires_pyarrow()
    pds = ParquetDataFrameStorage(base_path=str(tmp_path))
    df = pd.DataFrame({
        "symbol": ["BTCUSDT", "BTCUSDT"],
        "open_time": [datetime(2024, 1, 1, tzinfo=UTC),
                      datetime(2024, 1, 2, tzinfo=UTC)],
        "open": [100, 101],
        "high": [105, 106],
        "low": [95, 96],
        "close": [102, 103],
        "volume": [10, 11],
    })
    pds.store_ohlcv(df)
    loaded = pds.load_ohlcv("BTCUSDT")
    assert len(loaded) == 2
    assert list(loaded["symbol"]) == ["BTCUSDT", "BTCUSDT"]


def test_hybrid_storage_init():
    cfg = StorageConfig()
    hs = HybridStorage(cfg)
    assert hs.config == cfg
    assert hs._initialized is False


# --- ParquetDataFrameStorage extra behaviors ---------------------------------


def test_parquet_df_store_ohlcv_empty_returns_none(tmp_path):
    pds = ParquetDataFrameStorage(base_path=str(tmp_path))
    assert pds.store_ohlcv(pd.DataFrame()) is None
    assert pds.store_ohlcv(None) is None


def test_parquet_df_store_ohlcv_missing_symbol_raises(tmp_path):
    import importlib.util
    if importlib.util.find_spec("pyarrow") is None:
        pytest.skip("pyarrow not available")
    pds = ParquetDataFrameStorage(base_path=str(tmp_path))
    with pytest.raises(ValueError, match="symbol"):
        pds.store_ohlcv(pd.DataFrame({"open_time": [datetime(2024, 1, 1, tzinfo=UTC)]}))


def test_parquet_df_store_ohlcv_upsert_dedup(tmp_path):
    _requires_pyarrow()
    pds = ParquetDataFrameStorage(base_path=str(tmp_path))
    rows = []
    for symbol in ["BTCUSDT", "ETHUSDT"]:
        for day in (1, 2):
            rows.append({
                "symbol": symbol,
                "open_time": datetime(2024, 3, day, tzinfo=UTC),
                "close": 100.0 + day,
            })
    pds.store_ohlcv(pd.DataFrame(rows))
    # re-store same bars with updated close -> dedup by open_time, keep last
    rows[1]["close"] = 999.0
    pds.store_ohlcv(pd.DataFrame([rows[1]]))
    loaded = pds.load_ohlcv("BTCUSDT")
    assert len(loaded) == 2
    assert set(loaded["symbol"]) == {"BTCUSDT"}
    assert loaded.loc[loaded["open_time"].dt.day == 2, "close"].iloc[0] == 999.0


def test_parquet_df_load_ohlcv_empty_dir(tmp_path):
    pds = ParquetDataFrameStorage(base_path=str(tmp_path))
    assert pds.load_ohlcv("NOPE") is not None and pds.load_ohlcv("NOPE").empty


def test_parquet_df_load_ohlcv_timeframe_and_range(tmp_path):
    _requires_pyarrow()
    pds = ParquetDataFrameStorage(base_path=str(tmp_path))
    df = pd.DataFrame({
        "symbol": ["BTCUSDT"] * 3,
        "open_time": [datetime(2024, 1, 1, tzinfo=UTC),
                      datetime(2024, 1, 15, tzinfo=UTC),
                      datetime(2024, 2, 1, tzinfo=UTC)],
        "timeframe": ["1h", "1h", "1d"],
        "close": [1.0, 2.0, 3.0],
    })
    pds.store_ohlcv(df)
    out = pds.load_ohlcv("BTCUSDT", start=datetime(2024, 1, 5, tzinfo=UTC),
                         end=datetime(2024, 1, 31, tzinfo=UTC), timeframe="1h")
    assert len(out) == 1
    assert out["close"].iloc[0] == 2.0


def test_parquet_df_store_load_trades_roundtrip(tmp_path):
    _requires_pyarrow()
    pds = ParquetDataFrameStorage(base_path=str(tmp_path))
    df = pd.DataFrame({
        "symbol": ["BTCUSDT"] * 2,
        "trade_id": ["t1", "t2"],
        "time": [datetime(2024, 1, 1, 10, tzinfo=UTC),
                 datetime(2024, 1, 1, 11, tzinfo=UTC)],
        "price": [100.0, 101.0],
    })
    pds.store_trades(df)
    loaded = pds.load_trades("BTCUSDT")
    assert len(loaded) == 2
    assert set(loaded["trade_id"]) == {"t1", "t2"}


def test_parquet_df_store_trades_dedup_by_trade_id(tmp_path):
    _requires_pyarrow()
    pds = ParquetDataFrameStorage(base_path=str(tmp_path))
    df = pd.DataFrame({
        "symbol": ["BTCUSDT"],
        "trade_id": ["t1"],
        "time": [datetime(2024, 1, 1, 12, tzinfo=UTC)],
        "price": [100.0],
    })
    pds.store_trades(df)
    df2 = df.copy()
    df2.loc[0, "price"] = 150.0
    pds.store_trades(df2)
    loaded = pds.load_trades("BTCUSDT")
    assert len(loaded) == 1
    assert loaded["price"].iloc[0] == 150.0


def test_parquet_df_store_trades_empty(tmp_path):
    pds = ParquetDataFrameStorage(base_path=str(tmp_path))
    assert pds.store_trades(pd.DataFrame()) is None
    with pytest.raises(ValueError, match="symbol"):
        pds.store_trades(pd.DataFrame({"trade_id": ["x"]}))


def test_parquet_df_load_trades_empty_dir(tmp_path):
    pds = ParquetDataFrameStorage(base_path=str(tmp_path))
    assert pds.load_trades("NOPE").empty


# --- ParquetStorage (async buffers) -------------------------------------------


def _kline(ts: datetime, symbol: str = "BTCUSDT") -> dict:
    return {
        "open_time": ts, "symbol": symbol, "interval": "1m",
        "open_price": 100, "high_price": 101, "low_price": 99,
        "close_price": 100.5, "volume": 10, "trades": 5, "is_closed": True,
    }


def _ticker(ts: datetime, symbol: str = "BTCUSDT") -> dict:
    return {"timestamp": ts, "symbol": symbol, "price": 100.0}


def _trade(ts: datetime, symbol: str = "BTCUSDT") -> dict:
    return {"timestamp": ts, "symbol": symbol, "trade_id": f"t-{ts}",
            "price": 100.0, "quantity": 1, "side": "BUY", "is_maker": False}


def _rate(ts: datetime, symbol: str = "BTCUSDT") -> dict:
    return {"timestamp": ts, "symbol": symbol, "funding_rate": 0.0001,
            "mark_price": 100, "index_price": 99.9, "next_funding_time": ts}


@pytest.mark.asyncio
async def test_parquet_storage_write_and_read_klines(tmp_path):
    _requires_pyarrow()
    cfg = StorageConfig(parquet_base_path=str(tmp_path), batch_size=1000)
    ps = ParquetStorage(cfg)
    await ps.initialize()
    n = await ps.write_klines([
        _kline(datetime(2024, 1, 1, i * 5, tzinfo=UTC)) for i in range(3)
    ])
    assert n == 3
    await ps.flush_all()
    out = await ps.read_klines("BTCUSDT", "1m",
                               datetime(2024, 1, 1, tzinfo=UTC),
                               datetime(2024, 1, 2, tzinfo=UTC))
    assert len(out) == 3
    assert list(out["symbol"]) == ["BTCUSDT", "BTCUSDT", "BTCUSDT"]


@pytest.mark.asyncio
async def test_parquet_storage_flush_auto_on_batch_size(tmp_path):
    _requires_pyarrow()
    cfg = StorageConfig(parquet_base_path=str(tmp_path), batch_size=2)
    ps = ParquetStorage(cfg)
    await ps.initialize()
    await ps.write_klines([_kline(datetime(2024, 1, 1, i, tzinfo=UTC)) for i in range(2)])
    await asyncio.sleep(0.1)
    await ps.write_klines([_kline(datetime(2024, 1, 1, 9, tzinfo=UTC))])
    await ps.flush_all()
    out = await ps.read_klines("BTCUSDT", "1m",
                               datetime(2024, 1, 1, tzinfo=UTC),
                               datetime(2024, 1, 2, tzinfo=UTC))
    assert len(out) == 3


@pytest.mark.asyncio
async def test_parquet_storage_write_all_types(tmp_path):
    _requires_pyarrow()
    cfg = StorageConfig(parquet_base_path=str(tmp_path))
    ps = ParquetStorage(cfg)
    await ps.initialize()
    base = datetime(2024, 1, 1, 12, tzinfo=UTC)
    assert await ps.write_tickers([_ticker(base)]) == 1
    assert await ps.write_trades([_trade(base)]) == 1
    assert await ps.write_funding_rates([_rate(base)]) == 1
    await ps.flush_all()

    tick = await ps.read_tickers("BTCUSDT", base, base)
    assert len(tick) == 1
    assert tick["price"].iloc[0] == 100.0


@pytest.mark.asyncio
async def test_parquet_storage_read_no_data(tmp_path):
    _requires_pyarrow()
    cfg = StorageConfig(parquet_base_path=str(tmp_path))
    ps = ParquetStorage(cfg)
    await ps.initialize()
    base = datetime(2024, 1, 1, tzinfo=UTC)
    assert (await ps.read_klines("BTCUSDT", "1m", base, base)).empty
    assert (await ps.read_tickers("BTCUSDT", base, base)).empty


@pytest.mark.asyncio
async def test_parquet_storage_close_flushes(tmp_path, monkeypatch):
    _requires_pyarrow()
    cfg = StorageConfig(parquet_base_path=str(tmp_path))
    ps = ParquetStorage(cfg)
    await ps.initialize()
    flushed = []

    async def fake_flush_all():
        flushed.append(True)

    monkeypatch.setattr(ps, "flush_all", fake_flush_all)
    await ps.close()
    assert flushed == [True]


# --- TimescaleDBStorage (mocked pool) ---------------------------------------


class _FakePool:
    """Minimal async pool stand-in exposing acquire() as an async CM."""

    def __init__(self, records=None):
        self._records = records or []
        self.executemany_calls = []
        self.fetch_calls = []

    def acquire(self):
        return _FakeConn(self)

    async def close(self):
        pass


class _FakeConn:
    def __init__(self, pool):
        self._pool = pool

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, query):
        return None

    async def executemany(self, query, records):
        self._pool.executemany_calls.append((query, records))

    async def fetch(self, query, *args):
        self._pool.fetch_calls.append((query, args))
        rows = self._pool._records
        return [dict(r) for r in rows]


@pytest.mark.asyncio
async def test_timescale_write_empty_returns_zero(monkeypatch):
    ts = TimescaleDBStorage(StorageConfig())
    assert await ts.write_klines([]) == 0
    assert await ts.write_tickers([]) == 0
    assert await ts.write_trades([]) == 0
    assert await ts.write_funding_rates([]) == 0


@pytest.mark.asyncio
async def test_timescale_write_klines_builds_records():
    ts = TimescaleDBStorage(StorageConfig())
    pool = _FakePool()
    ts.pool = pool
    base = datetime(2024, 1, 1, tzinfo=UTC)
    k = _kline(base)
    n = await ts.write_klines([k])
    assert n == 1
    assert len(pool.executemany_calls) == 1
    query, records = pool.executemany_calls[0]
    assert "INSERT INTO klines" in query
    assert len(records) == 1
    assert records[0][0] == base


@pytest.mark.asyncio
async def test_timescale_write_all_types():
    ts = TimescaleDBStorage(StorageConfig())
    pool = _FakePool()
    ts.pool = pool
    base = datetime(2024, 1, 1, tzinfo=UTC)
    assert await ts.write_tickers([_ticker(base)]) == 1
    assert await ts.write_trades([_trade(base)]) == 1
    assert await ts.write_funding_rates([_rate(base)]) == 1
    assert len(pool.executemany_calls) == 3  # one batch per type
    queries = " ".join(q for q, _ in pool.executemany_calls)
    assert "INSERT INTO tickers" in queries
    assert "INSERT INTO trades" in queries
    assert "INSERT INTO funding_rates" in queries


@pytest.mark.asyncio
async def test_timescale_read_klines_and_tickers():
    ts = TimescaleDBStorage(StorageConfig())
    pool = _FakePool([{"time": datetime(2024, 1, 1, tzinfo=UTC), "symbol": "BTCUSDT",
                       "price": 100.0}])
    ts.pool = pool
    base = datetime(2024, 1, 1, tzinfo=UTC)
    out = await ts.read_klines("BTCUSDT", "1m", base, base + timedelta(hours=1))
    assert isinstance(out, pd.DataFrame)
    df = await ts.read_tickers("BTCUSDT", base, base + timedelta(hours=1))
    assert df["price"].iloc[0] == 100.0


@pytest.mark.asyncio
async def test_timescale_close_when_pool_none():
    ts = TimescaleDBStorage(StorageConfig())
    ts.pool = None
    assert await ts.close() is None


@pytest.mark.asyncio
async def test_timescale_close_with_pool():
    ts = TimescaleDBStorage(StorageConfig())
    pool = _FakePool()
    ts.pool = pool
    await ts.close()
    assert ts.pool is not None


# --- HybridStorage routing ---------------------------------------------------


@pytest.mark.asyncio
async def test_hybrid_storage_routes_recent_to_tsdb(monkeypatch):
    cfg = StorageConfig()
    hs = HybridStorage(cfg)
    calls = {"recent": 0, "historical": 0, "split": 0}

    async def fake_recent_tsdb(symbol, timeframe, start, end):
        calls["recent"] += 1
        return pd.DataFrame()

    async def fake_recent_parquet(symbol, timeframe, start, end):
        calls["historical"] += 1
        return pd.DataFrame()

    monkeypatch.setattr(hs.tsdb, "read_klines", fake_recent_tsdb)
    monkeypatch.setattr(hs.parquet, "read_klines", fake_recent_parquet)

    now = datetime.now(UTC)
    await hs.read_klines("BTCUSDT", "1m", now, now)
    assert calls["recent"] == 1


@pytest.mark.asyncio
async def test_hybrid_storage_read_split(monkeypatch):
    cfg = StorageConfig()
    hs = HybridStorage(cfg)
    now = datetime.now(UTC)
    start = now - timedelta(days=60)
    end = now

    async def fake_tsdb(symbol, timeframe, s, e):
        return pd.DataFrame({"open_time": [s], "src": ["tsdb"]})

    async def fake_pq(symbol, timeframe, s, e):
        return pd.DataFrame({"open_time": [s], "src": ["pq"]})

    monkeypatch.setattr(hs.tsdb, "read_klines", fake_tsdb)
    monkeypatch.setattr(hs.parquet, "read_klines", fake_pq)
    out = await hs.read_klines("BTCUSDT", "1m", start, end)
    assert len(out) == 2


@pytest.mark.asyncio
async def test_hybrid_storage_write_delegates(monkeypatch):
    cfg = StorageConfig()
    hs = HybridStorage(cfg)
    tsdb_calls = []
    pq_calls = []

    async def fake_ts(klines):
        tsdb_calls.append(klines)
        return len(klines)

    async def fake_pq(klines):
        pq_calls.append(klines)
        return len(klines)

    monkeypatch.setattr(hs.tsdb, "write_klines", fake_ts)
    monkeypatch.setattr(hs.parquet, "write_klines", fake_pq)

    n = await hs.write_klines([_kline(datetime(2024, 1, 1, tzinfo=UTC))])
    assert n == 1
    assert tsdb_calls and pq_calls


@pytest.mark.asyncio
async def test_hybrid_read_tickers_recent(monkeypatch):
    cfg = StorageConfig()
    hs = HybridStorage(cfg)
    now = datetime.now(UTC)
    called = {}

    async def fake_ts(symbol, start, end):
        called["tsdb"] = True
        return pd.DataFrame({"time": [start]})

    monkeypatch.setattr(hs.tsdb, "read_tickers", fake_ts)
    await hs.read_tickers("BTCUSDT", now, now)
    assert called.get("tsdb")


# --- global storage ---------------------------------------------------------


def test_get_storage_singleton(monkeypatch):
    import cryptobot.data.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_storage", None)
    first = storage_mod.get_storage(StorageConfig())
    second = storage_mod.get_storage()
    assert first is second


def test_get_storage_uses_settings_when_no_config(monkeypatch):
    import cryptobot.data.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_storage", None)
    storage = storage_mod.get_storage()
    assert isinstance(storage, HybridStorage)


@pytest.mark.asyncio
async def test_init_and_shutdown_storage(monkeypatch):
    import cryptobot.data.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_storage", None)
    cfg = StorageConfig()
    init_calls = []
    close_calls = []

    async def fake_init():
        init_calls.append(True)

    async def fake_close():
        close_calls.append(True)

    storage = storage_mod.get_storage(cfg)
    monkeypatch.setattr(storage, "initialize", fake_init)
    monkeypatch.setattr(storage, "close", fake_close)
    result = await storage_mod.init_storage(cfg)
    assert result is storage
    assert init_calls == [True]
    await storage_mod.shutdown_storage()
    assert close_calls == [True]
    assert storage_mod._storage is None


@pytest.mark.asyncio
async def test_shutdown_storage_when_none(monkeypatch):
    import cryptobot.data.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_storage", None)
    await storage_mod.shutdown_storage()
    assert storage_mod._storage is None


__all__ = []
