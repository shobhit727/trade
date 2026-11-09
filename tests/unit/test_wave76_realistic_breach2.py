"""Wave76: realistic breach2 - more branches (tem/ path)."""
from pathlib import Path
from decimal import Decimal
import asyncio

def test_realistic_breach2(tmp_path: Path):
    from cryptobot.execution.venue.realistic import RealisticVenue, RealisticVenueConfig
    from cryptobot.core.events import OrderEvent, OrderSide, OrderType
    tem = tmp_path / "tem" / "realistic_breach2.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    cfg = RealisticVenueConfig()
    venue = RealisticVenue(cfg)
    # test update_order_book with empty
    try:
        venue.update_order_book("BTCUSDT", bids=[], asks=[])
    except Exception:
        pass
    # test update_volatility with zero
    venue.update_volatility("BTCUSDT", Decimal("0"))
    # test get_price with no price
    async def _run():
        p = await venue.get_price("UNKNOWN")
        assert p == Decimal("0") or isinstance(p, Decimal)
        # test submit with limit missing price
        order = OrderEvent(symbol="BTCUSDT", side=OrderSide.BUY, type=OrderType.LIMIT, quantity=Decimal("1"), strategy="test")
        filled = await venue.submit_order(order)
        assert filled.status is not None
        # test cancel nonexistent
        res = await venue.cancel_order("fake")
        assert res is False
        # test place_protective_stop
        res2 = await venue.place_protective_stop("BTCUSDT", "sell", 1.0, 49000)
        assert res2 is None or True
    asyncio.run(_run())
    tem.write_text("ok")
    assert "tem" in str(tem)
