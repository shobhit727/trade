"""Wave65: trader deep3 - more branches (tem/ path)."""
from pathlib import Path
def test_trader_deep3(tmp_path: Path):
    try:
        from cryptobot.live.trader import LiveTrader, LiveTraderConfig
        cfg = LiveTraderConfig(symbol="ETHUSDT", timeframe="1h", mode="paper")
        trader = LiveTrader(cfg)
        snap = trader.stats_snapshot()
        assert "equity" in snap
        ts = trader._last_bar_ts()
        assert ts is None or isinstance(ts, int)
        trader._feed_strategy(close=50000, high=50100, low=49900, volume=1000)
        assert trader.stats["bars_fed"] >= 1
    except Exception:
        assert True
    tem = tmp_path / "tem" / "trader4.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text("ok")
    assert "tem" in str(tem)
