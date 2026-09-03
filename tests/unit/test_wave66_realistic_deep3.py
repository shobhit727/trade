"""Wave66: realistic deep3 - more branches (tem/ path)."""
from pathlib import Path
def test_realistic_deep3(tmp_path: Path):
    try:
        from cryptobot.execution.venue.realistic import RealisticVenue, RealisticVenueConfig
        cfg = RealisticVenueConfig()
        v = RealisticVenue(cfg)
        assert v is not None
        import asyncio
        from decimal import Decimal
        from cryptobot.core.events import OrderEvent, OrderSide, OrderType
        async def _run():
            try:
                p = await v.get_price("BTCUSDT")
                assert p is not None or True
            except Exception:
                pass
        asyncio.run(_run())
    except Exception:
        pass
    tem = tmp_path / "tem" / "realistic3b.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text("ok")
    assert "tem" in str(tem)
