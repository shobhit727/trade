"""Core clock extra2: SimulatedClock edge (tem/ path)."""

from pathlib import Path
from datetime import datetime, timezone, timedelta
import asyncio

def test_clock_extra2(tmp_path: Path):
    from cryptobot.core.clock import SimulatedClock, ClockFactory, ClockConfig, ClockMode
    start = datetime(2024,1,1, tzinfo=timezone.utc)
    sc = SimulatedClock(start_time=start, end_time=start+timedelta(hours=1))
    # test pause/resume
    sc.pause()
    assert sc.is_paused is True
    sc.resume()
    assert sc.is_paused is False
    # test get_elapsed/remaining
    assert sc.get_elapsed() == timedelta(0)
    assert sc.get_remaining() is not None
    # test ClockFactory
    cfg = ClockConfig(mode=ClockMode.REALTIME)
    c = ClockFactory.create(cfg)
    assert c.mode == ClockMode.REALTIME
    tem = tmp_path / "tem" / "clock2.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text("ok")
    assert "tem" in str(tem)
