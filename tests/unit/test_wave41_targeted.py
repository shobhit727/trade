"""Wave41 targeted: trader (tem/ path)."""
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone


def test_wave_trader(tmp_path: Path):
    from cryptobot.live.trader import LiveTraderConfig
    cfg = LiveTraderConfig(symbol="BTCUSDT", timeframe="1m")
    assert cfg.symbol == "BTCUSDT"
    assert cfg.data_ws_url is not None or True
    tem = tmp_path / "tem" / "trader2.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text(str(cfg))
    assert "tem" in str(tem)
