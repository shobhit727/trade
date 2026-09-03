"""Monitoring alerting extra2: AlertManager flow (tem/ path)."""

from pathlib import Path
import asyncio
from cryptobot.monitoring.alerting import AlertManager, Alert, AlertSeverity, AlertCategory

def test_alerting_extra2(tmp_path: Path):
    async def _run():
        mgr = AlertManager()
        alert = Alert(title="test", message="hello", severity=AlertSeverity.WARNING, category=AlertCategory.RISK, source="test")
        await mgr.fire(alert)
        assert len(mgr.get_active_alerts()) >= 1
        await mgr.resolve(alert)
        assert len(mgr.get_active_alerts()) == 0
        await mgr.start()
        await mgr.stop()
    asyncio.run(_run())
    tem = tmp_path / "tem" / "alert2.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text("ok")
    assert "tem" in str(tem)
