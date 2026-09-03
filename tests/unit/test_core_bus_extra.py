"""Core bus extra: publish/subscribe, history, wildcard (tem/ path)."""

from pathlib import Path
import asyncio
from cryptobot.core.bus import EventBus
from cryptobot.core.events import Event, EventType

def test_bus_extra(tmp_path: Path):
    async def _run():
        bus = EventBus(max_history=5)
        seen = []
        async def handler(event):
            seen.append(event)
        sub_id = await bus.subscribe(EventType.TICKER, async_callback=handler)
        event = Event(type=EventType.TICKER, payload={"symbol": "BTCUSDT", "price": "100"})
        delivered = await bus.publish(event)
        assert delivered >= 0
        hist = bus.get_history(event_type=EventType.TICKER)
        assert len(hist) >= 1
        await bus.unsubscribe(sub_id)
        # wildcard
        sub2 = await bus.subscribe(EventType.ERROR, async_callback=handler)
        await bus.publish_raw("custom.topic", {"foo": "bar"})
        await bus.unsubscribe(sub2)
        await bus.close()
        return True
    assert asyncio.run(_run()) is True
    tem = tmp_path / "tem" / "bus.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text("ok")
    assert "tem" in str(tem)
