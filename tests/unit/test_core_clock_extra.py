"""Core clock extra: realtime, simulated, accelerated (tem/ path)."""

from pathlib import Path
from datetime import datetime, timezone, timedelta
import asyncio
from cryptobot.core.clock import ClockFactory, ClockConfig, ClockMode, SimulatedClock, RealtimeClock, AcceleratedClock

def test_clock_extra(tmp_path: Path):
    # realtime
    rc = RealtimeClock()
    assert rc.now() is not None
    # simulated
    start = datetime(2024,1,1, tzinfo=timezone.utc)
    end = datetime(2024,1,2, tzinfo=timezone.utc)
    sc = SimulatedClock(start_time=start, end_time=end)
    assert sc.current_time == start
    async def _run():
        await sc.step(timedelta(seconds=60))
        assert sc.current_time == start + timedelta(seconds=60)
        await sc.step_to(end)
        assert sc.is_finished() is True
        sc.reset(start)
        assert sc.current_time == start
    asyncio.run(_run())
    # factory
    cfg = ClockConfig(mode=ClockMode.SIMULATED, start_time=start, end_time=end)
    c = ClockFactory.create(cfg)
    assert c is not None
    # accelerated
    ac = AcceleratedClock(speed_factor=10.0)
    assert ac.now() is not None
    tem = tmp_path / "tem" / "clock.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text("ok")
    assert "tem" in str(tem)
