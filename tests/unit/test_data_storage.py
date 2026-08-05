from __future__ import annotations

from datetime import UTC, datetime

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


def test_parquet_dataframe_storage_store_ohlcv(tmp_path):
    import pandas as pd
    import pytest
    try:
        import importlib.util
        if importlib.util.find_spec("pyarrow") is None:
            pytest.skip("pyarrow not available")
    except ImportError:
        pytest.skip("pyarrow not available")
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
    import pandas as pd
    import pytest
    try:
        import importlib.util
        if importlib.util.find_spec("pyarrow") is None:
            pytest.skip("pyarrow not available")
    except ImportError:
        pytest.skip("pyarrow not available")
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


__all__ = []
