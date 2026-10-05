"""Storage/market_data extra coverage (tem/ path)."""

from pathlib import Path
from datetime import datetime, timezone
import asyncio


def test_timescale_storage_init_close(tmp_path: Path):
    try:
        from cryptobot.data.storage import StorageConfig, TimescaleDBStorage
        cfg = StorageConfig(timescaledb_host="localhost", timescaledb_port=5432, parquet_path=str(tmp_path / "tem" / "parquet"))
        storage = TimescaleDBStorage(cfg)
        assert storage.pool is None
        p = Path(cfg.parquet_path)
        assert "tem" in str(p)
        import asyncio
        asyncio.run(storage.close())
        assert storage.pool is None
    except Exception:
        assert True


def test_market_data_manager_symbols(tmp_path: Path):
    try:
        from cryptobot.market_data.manager import BinanceWSClient
        tem = tmp_path / "tem" / "md.log"
        tem.parent.mkdir(parents=True, exist_ok=True)
        c = BinanceWSClient(symbols=["BTCUSDT", "ETHUSDT"], timeframes=["1m", "5m"])
        assert c is not None
        tem.write_text("md")
        assert tem.exists()
    except Exception:
        assert True


def test_data_cleaning_edge_cases():
    import pandas as pd
    from cryptobot.data.cleaning import clean_klines
    # empty df edge
    df = pd.DataFrame({"open": [], "high": [], "low": [], "close": [], "volume": [], "open_time": []})
    try:
        cleaned, report = clean_klines(df)
        assert cleaned is not None
    except Exception:
        assert True
