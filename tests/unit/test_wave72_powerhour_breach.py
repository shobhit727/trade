"""Wave72: powerhour breach - enter/exit loop (tem/ path)."""
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch

def test_powerhour_breach(tmp_path: Path):
    from cryptobot.live.nse_powerhour import PowerHourTrader
    tem = tmp_path / "tem" / "ph_breach.json"
    tem.parent.mkdir(parents=True, exist_ok=True)
    trader = PowerHourTrader(symbols=["T"], capital=100000, state_file=tem)
    base = datetime(2024,1,1, tzinfo=timezone.utc)
    def fake_bars(sym):
        bars = []
        for i in range(25):
            off = i * 15
            hh = 9 + off // 60
            mm = off % 60
            # create bars with rising close to trigger power_hour
            close = 100 + i*0.2
            bars.append({"ts": int(base.timestamp()*1000)+i*900000, "date": "2024-01-01", "mod": hh*60+mm, "open": close-0.1, "high": close+0.3, "low": close-0.3, "close": close, "volume": 1000+i*10})
        return bars
    with patch("cryptobot.live.nse_powerhour.fetch_bars", side_effect=fake_bars):
        res = trader.enter_phase()
        assert isinstance(res, dict)
        # check snapshot
        snap = trader.snapshot()
        assert "equity" in snap
        # exit
        res2 = trader.exit_phase()
        assert isinstance(res2, dict)
        # dashboard
        html = trader._dashboard_html()
        assert "Power Hour" in html
        # next_at
        target, wait = trader._next_at(14, 0)
        assert wait > 0
    assert "tem" in str(tem)
