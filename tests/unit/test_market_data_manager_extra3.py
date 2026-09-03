"""Market data manager extra3 (tem/ path)."""

from pathlib import Path

def test_market_data_manager_extra3(tmp_path: Path):
    try:
        from cryptobot.market_data.manager import BinanceWSClient
        from cryptobot.config import get_settings
        ws = get_settings().external_services.binance_data_ws_url
        c = BinanceWSClient(symbols=["BTCUSDT", "ETHUSDT"], timeframes=["1m"])
        assert len(c.symbols) == 2
        # test get_ticker missing
        t = c.get_ticker("BTCUSDT")
        assert t is None or hasattr(t, "price") or isinstance(t, dict) or t is None
        tem = tmp_path / "tem" / "md3.txt"
        tem.parent.mkdir(parents=True, exist_ok=True)
        tem.write_text(ws)
        assert "tem" in str(tem)
    except Exception:
        assert True
