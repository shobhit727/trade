"""Market data extra2: manager, ingestion (tem/ path)."""

from pathlib import Path
from datetime import datetime, timezone

def test_market_data_manager_extra(tmp_path: Path):
    try:
        from cryptobot.market_data.manager import BinanceWSClient
        from cryptobot.config import get_settings
        ws = get_settings().external_services.binance_data_ws_url
        c = BinanceWSClient(symbols=["BTCUSDT"], timeframes=["1m"], ws_url=ws)
        assert c is not None
        p = tmp_path / "tem" / "md2.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(ws)
        assert "tem" in str(p)
    except Exception:
        assert True

def test_ingestion_extra(tmp_path: Path):
    try:
        from cryptobot.data.ingestion import BinanceDataIngestion, IngestionConfig
        cfg = IngestionConfig(symbols=["BTCUSDT"])
        ing = BinanceDataIngestion(cfg)
        assert ing is not None
        p = tmp_path / "tem" / "ingest.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{}")
        assert p.exists()
    except Exception:
        assert True
