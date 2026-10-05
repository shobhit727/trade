"""Wave62: powerhour deep2 - loop, snapshot, dashboard (tem/ path)."""
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch

def test_powerhour_deep2(tmp_path: Path):
    from cryptobot.live.nse_powerhour import PowerHourTrader, PowerHourState
    tem = tmp_path / "tem" / "ph3.json"
    tem.parent.mkdir(parents=True, exist_ok=True)
    trader = PowerHourTrader(symbols=["T"], capital=100000, state_file=tem)
    # test snapshot with positions
    trader.state.positions["T"] = {"qty": 10, "entry": 100, "sym": "T"}
    trader._marks["T"] = 105
    snap = trader.snapshot()
    assert snap["open_positions"] == 1
    assert snap["equity"] is not None
    # test _next_at
    target, wait = trader._next_at(14, 0)
    assert wait > 0
    # test dashboard html
    html = trader._dashboard_html()
    assert "Power Hour" in html
    # test reset breaker
    trader.state.breaker_tripped = True
    trader.state.breaker_reason = "test"
    trader.reset_breaker()
    assert trader.state.breaker_tripped is False
    assert "tem" in str(tem)
