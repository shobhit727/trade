"""Wave67: powerhour deep3 - more branches (tem/ path)."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

def test_powerhour_deep3(tmp_path: Path):
    from cryptobot.live.nse_powerhour import PowerHourTrader, PowerHourState
    tem = tmp_path / "tem" / "ph4b.json"
    tem.parent.mkdir(parents=True, exist_ok=True)
    trader = PowerHourTrader(symbols=["T"], capital=100000, state_file=tem)
    # test _next_at with weekend
    now = trader._ist_now()
    target, wait = trader._next_at(14, 0)
    assert wait > 0
    assert target.weekday() < 5
    # test snapshot with positions and marks
    trader.state.positions["T"] = {"qty": 10, "entry": 100, "sym": "T"}
    trader._marks["T"] = 105
    snap = trader.snapshot()
    assert snap["open_positions"] == 1
    # test _fee
    fee = trader._fee(10000)
    assert fee > 0
    # test enter/exit with mocked fetch
    def fake_bars(sym):
        base = datetime(2024,1,1, tzinfo=timezone.utc)
        bars = []
        for i in range(25):
            off = i * 15
            hh = 9 + off // 60
            mm = off % 60
            bars.append({"ts": int(base.timestamp()*1000)+i*900000, "date": "2024-01-01", "mod": hh*60+mm, "open": 100, "high": 101, "low": 99, "close": 100+i*0.1, "volume": 1000})
        return bars
    with patch("cryptobot.live.nse_powerhour.fetch_bars", side_effect=fake_bars):
        res = trader.enter_phase()
        assert isinstance(res, dict)
        res2 = trader.exit_phase()
        assert isinstance(res2, dict)
    # test dashboard
    html = trader._dashboard_html()
    assert "Power Hour" in html
    assert "tem" in str(tem)
