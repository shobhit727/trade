"""Wave57: powerhour deep (tem/ path)."""

from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch

def test_powerhour_deep(tmp_path: Path):
    from cryptobot.live.nse_powerhour import PowerHourTrader
    tem = tmp_path / "tem" / "ph_deep.json"
    tem.parent.mkdir(parents=True, exist_ok=True)
    trader = PowerHourTrader(symbols=["T"], capital=100000, state_file=tem)
    # mock fetch_bars to return a session
    def fake_bars(sym):
        base = datetime(2024,1,1, tzinfo=timezone.utc)
        # create 25 bars for a session 09:15->15:30
        bars = []
        for i in range(25):
            off = i * 15
            hh = 9 + off // 60
            mm = off % 60
            # need mod field for powerhour logic
            bars.append({"ts": int(base.timestamp()*1000)+i*900000, "date": "2024-01-01", "mod": hh*60+mm, "open": 100, "high": 101, "low": 99, "close": 100+i*0.1, "volume": 1000})
        return bars
    with patch("cryptobot.live.nse_powerhour.fetch_bars", side_effect=fake_bars):
        res = trader.enter_phase()
        assert isinstance(res, dict)
        res2 = trader.exit_phase()
        assert isinstance(res2, dict)
        snap = trader.snapshot()
        assert snap["status"] == "running"
    assert "tem" in str(tem)
