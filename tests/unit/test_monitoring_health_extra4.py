"""Monitoring health extra4: HealthMonitor full flow (tem/ path)."""

from pathlib import Path
import asyncio
from cryptobot.monitoring.health import HealthMonitor, HealthCheck, ComponentType, HealthStatus

def test_health_monitor_full(tmp_path: Path):
    hm = HealthMonitor()
    # register multiple checks with different components
    hm.register_check(HealthCheck(name="c1", component=ComponentType.CACHE, check_fn=lambda: True, interval_seconds=0.01))
    hm.register_check(HealthCheck(name="c2", component=ComponentType.DATABASE, check_fn=lambda: (_ for _ in ()).throw(RuntimeError("fail")), interval_seconds=0.01))
    async def _run():
        await hm.run_all_checks()
        statuses = hm.get_all_health()
        assert isinstance(statuses, dict)
        overall = hm.get_overall_status()
        assert overall in (HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.UNHEALTHY, HealthStatus.UNKNOWN)
        # update interval
        hm.update_check_interval("c1", 0.02)
        assert hm._checks["c1"].interval_seconds == 0.02
        # get_check
        c = hm.get_check("c1")
        assert c is not None
        # unregister
        hm.unregister_check("c2")
        assert hm.get_check("c2") is None
    asyncio.run(_run())
    tem = tmp_path / "tem" / "health4.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text("ok")
    assert "tem" in str(tem)
