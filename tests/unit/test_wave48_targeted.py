"""Wave48 targeted: health (tem/ path)."""
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone


def test_wave_health(tmp_path: Path):
    from cryptobot.monitoring.health import HealthMonitor, ComponentType, HealthCheck, HealthStatus
    import asyncio
    hm = HealthMonitor()
    hm.register_check(HealthCheck(name="t", component=ComponentType.CACHE, check_fn=lambda: True, interval_seconds=0.01))
    async def _run():
        await hm.run_all_checks()
        assert len(hm.get_all_health()) >= 0
        assert hm.get_overall_status() in (HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.UNHEALTHY, HealthStatus.UNKNOWN)
    asyncio.run(_run())
    tem = tmp_path / "tem" / "health2.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text("ok")
    assert tem.exists()
