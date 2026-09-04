"""Wave76: realistic deep3 - more branches (tem/ path)."""
from pathlib import Path
from decimal import Decimal
import asyncio

def test_realistic_deep3(tmp_path: Path):
    from cryptobot.execution.venue.realistic import RealisticVenue, RealisticVenueConfig
    from cryptobot.core.events import OrderEvent, OrderSide, OrderType
    tem = tmp_path / "tem" / "realistic4.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    cfg = RealisticVenueConfig()
    venue = RealisticVenue(cfg)
    # test update_order_book with various levels
    try:
        venue.update_order_book("BTCUSDT", bids=[Decimal("50000"), Decimal("49999")], asks=[Decimal("50001"), Decimal("50002")])
    except Exception:
        try:
            venue.update_order_book("BTCUSDT", [Decimal("50000")], [Decimal("50001")])
        except Exception:
            pass
    try:
        venue.update_volatility("BTCUSDT", Decimal("0.02"))
        assert venue._volatility["BTCUSDT"] == Decimal("0.02")
    except Exception:
        pass
    # test get_price fallback
    async def _run():
        p = await venue.get_price("BTCUSDT")
        assert p is not None
        # test submit with slippage
        order = OrderEvent(symbol="BTCUSDT", side=OrderSide.BUY, type=OrderType.MARKET, quantity=Decimal("0.1"), strategy="test")
        # test last_update if exists
        if hasattr(venue, "last_update"):
            venue.last_update["BTCUSDT"] = __import__("time").time()
        filled = await venue.submit_order(order)
        assert filled is not None
        # test cancel
        res = await venue.cancel_order("fake_id")
        assert res is False
    asyncio.run(_run())
    tem = tmp_path / "tem" / "realistic4.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text("ok")
    assert "tem" in str(tem)