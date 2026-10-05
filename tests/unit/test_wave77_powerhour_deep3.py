"""Wave77: powerhour deep3 - more branches (tem/ path)."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

def test_powerhour_deep3(tmp_path: Path):
    from cryptobot.live.nse_powerhour import PowerHourTrader, PowerHourState
    tem = tmp_path / "tem" / "ph4b.json"
    tem.parent.mkdir(parents=True, exist_ok=True)
    trader = PowerHourTrader(symbols=["T"], capital=100000, state_file=tem)
    # test _ist_now, _next_at, loop helpers
    now = trader._ist_now()
    assert now is not None
    target, wait = trader._next_at(15, 30)
    assert wait > 0
    # test snapshot with empty positions
    snap = trader.snapshot()
    assert snap["status"] == "running"
    # test dashboard
    html = trader._dashboard_html()
    assert "Power Hour" in html
    # test reset breaker
    trader.state.breaker_tripped = True
    trader.state.breaker_reason = "test"
    trader.reset_breaker()
    assert trader.state.breaker_tripped is False
    assert "tem" in str(tem)