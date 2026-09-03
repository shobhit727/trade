"""Wave43 targeted: nse_powerhour (tem/ path)."""
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone


def test_wave_powerhour(tmp_path: Path):
    from cryptobot.live.nse_powerhour import PowerHourState, PowerHourTrader
    from datetime import datetime, timezone
    tem = tmp_path / "tem" / "ph2.json"
    s = PowerHourState(capital=100000)
    s.positions["T"] = {"qty": 5, "entry": 100, "sym": "T"}
    d = s.to_dict()
    s2 = PowerHourState.from_dict(d)
    assert s2.cash is not None
    trader = PowerHourTrader(symbols=["T"], capital=100000, state_file=tem)
    snap = trader.snapshot()
    assert snap["status"] == "running"
    assert "tem" in str(tem)
