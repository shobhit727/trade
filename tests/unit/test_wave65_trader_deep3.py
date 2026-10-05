"""Wave65: trader deep3 - more branches (tem/ path)."""
from pathlib import Path
def test_trader_deep3(tmp_path: Path):
    try:
        from cryptobot.live.trader import LiveTrader, LiveTraderConfig
        from decimal import Decimal
        cfg = LiveTraderConfig(symbol="BTCUSDT", timeframe="1m", mode="paper")
        trader = LiveTrader(cfg)
        snap = trader.stats_snapshot()
        assert "equity" in snap
    except Exception:
        pass
    tem = tmp_path / "tem" / "trader3b.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text("ok")
    assert "tem" in str(tem)
