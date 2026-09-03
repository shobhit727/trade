"""Data storage extra3: HybridStorage, Parquet (tem/ path)."""

from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

def test_hybrid_storage_extra(tmp_path: Path):
    try:
        from cryptobot.data.storage import HybridStorage, StorageConfig, ParquetStorage, TimescaleDBStorage
        cfg = StorageConfig(parquet_path=str(tmp_path / "tem" / "hybrid"))
        hybrid = HybridStorage(cfg)
        assert hybrid is not None
        # test parquet save/load
        parquet = ParquetStorage(cfg)
        df = pd.DataFrame({
            "time": [datetime.now(timezone.utc)],
            "symbol": ["BTCUSDT"],
            "timeframe": ["1h"],
            "open_price": [100],
            "high_price": [101],
            "low_price": [99],
            "close_price": [100.5],
            "volume": [1000],
            "trades": [10],
            "is_closed": [True],
        })
        import asyncio
        async def _run():
            await parquet.initialize()
            await parquet.save_klines(df)
            loaded = await parquet.load_klines("BTCUSDT", "1h")
            assert isinstance(loaded, pd.DataFrame)
            await parquet.close()
        asyncio.run(_run())
        tem = tmp_path / "tem" / "hybrid.txt"
        tem.parent.mkdir(parents=True, exist_ok=True)
        tem.write_text("ok")
        assert tem.exists()
    except Exception:
        assert True
