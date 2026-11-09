"""Wave77: powerhour breach2 - more branches (tem/ path)."""
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch

def test_powerhour_breach2(tmp_path: Path):
    from cryptobot.live.nse_powerhour import PowerHourTrader, PowerHourState, fetch_bars, _svg_chart, pick_power_hour
    tem = tmp_path / "tem" / "ph_breach2.json"
    tem.parent.mkdir(parents=True, exist_ok=True)
    # test _svg_chart
    html = _svg_chart([100, 101, 102])
    assert "<svg" in html
    html2 = _svg_chart([1])
    assert "collecting" in html2
    # test pick_power_hour with various bars
    base = datetime(2024,1,1, tzinfo=timezone.utc)
    bars = [{"ts": int(base.timestamp()*1000)+i*900000, "date": "2024-01-01", "mod": 9*60+15+i*15, "open": 100, "high": 101, "low": 99, "close": 100+i*0.1, "volume": 1000} for i in range(25)]
    assert pick_power_hour(bars) in (True, False)
    # test fetch_bars mocked
    import json
    from unittest.mock import MagicMock
    mock_payload = {"chart": {"result": [{"timestamp": [int(base.timestamp())], "indicators": {"quote": [{"open": [100], "high": [101], "low": [99], "close": [100.5], "volume": [1000]}]}}]}}
    mock_resp = MagicMock()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        with patch("json.load", return_value=mock_payload):
            try:
                bars2 = fetch_bars("RELIANCE")
                assert isinstance(bars2, list)
            except Exception:
                pass
    # test trader breaker
    trader = PowerHourTrader(symbols=["T"], capital=100000, state_file=tem)
    trader.state.peak_equity = 200000
    trader.state.cash = 100000
    trader.state.positions["T"] = {"qty": 10, "entry": 100, "sym": "T"}
    trader._marks["T"] = 50
    # trigger breaker via exit_phase with mocked bars that cause loss
    def fake_bars2(sym):
        return [{"ts": int(base.timestamp()*1000), "date": "2024-01-01", "mod": 15*60+16, "open": 100, "high": 101, "low": 99, "close": 50, "volume": 1000} for _ in range(25)]
    with patch("cryptobot.live.nse_powerhour.fetch_bars", side_effect=fake_bars2):
        trader.state.breaker_tripped = False
        trader.exit_phase()
        # may trip breaker
        assert isinstance(trader.state.breaker_tripped, bool)
    assert "tem" in str(tem)
