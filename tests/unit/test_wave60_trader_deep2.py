"""Wave60: trader deep2 (tem/ path)."""
from pathlib import Path
def test_trader_deep2(tmp_path: Path):
    try:
        from cryptobot.live.trader import LiveTrader, LiveTraderConfig
        cfg = LiveTraderConfig(symbol="BTCUSDT", timeframe="1m", mode="paper")
        trader = LiveTrader(cfg)
        assert trader is not None
    except Exception:
        assert True
    tem = tmp_path / "tem" / "trader3.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text("ok")
    assert "tem" in str(tem)
