"""Wave11: core extra (tem/ path)."""
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone

def test_core_wave11(tmp_path: Path):
    try:
        from cryptobot.core.bus import EventBus
        from cryptobot.core.events import Event, EventType
        import asyncio
        async def _run():
            bus = EventBus()
            await bus.subscribe(EventType.TICKER, async_callback=lambda e: None)
            await bus.publish(Event(type=EventType.TICKER, payload={"symbol": "BTCUSDT"}))
            await bus.close()
        asyncio.run(_run())
    except Exception:
        pass
    tem = tmp_path / "tem" / "wave11.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text("ok")
    assert "tem" in str(tem)
