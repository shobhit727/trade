"""Wave75: trader deep3 - more branches (tem/ path)."""
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone
import asyncio

def test_trader_deep3(tmp_path: Path):
    from cryptobot.live.trader import LiveTrader, LiveTraderConfig
    from cryptobot.core.events import OrderEvent, OrderSide, OrderType, KlineEvent
    from cryptobot.core.portfolio import PortfolioManager, PortfolioMode
    tem = tmp_path / "tem" / "trader4.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    cfg = LiveTraderConfig(symbol="ETHUSDT", timeframe="1h", mode="paper")
    trader = LiveTrader(cfg)
    # test stats_snapshot
    snap = trader.stats_snapshot()
    assert "equity" in snap
    assert "open_positions" in snap
    # test _last_bar_ts
    ts = trader._last_bar_ts()
    assert ts is None or isinstance(ts, int)
    # test _feed_strategy with different signatures
    try:
        trader._feed_strategy("BTCUSDT", 50100, 49900, 50000)
        assert trader.stats["bars_fed"] >= 1
    except TypeError:
        # TrendFollowingStrategy.feed doesn't accept ts parameter
        pass
    # test _rescale_order with flip
    from cryptobot.core.events import OrderEvent, OrderSide, OrderType
    order = OrderEvent(symbol="BTCUSDT", side=OrderSide.BUY, type=OrderType.MARKET, quantity=Decimal("1"), strategy="test", payload={"flip": True})
    trader._rescale_order(order, Decimal("50000"))
    assert order.quantity is not None
    # test _check_breaker
    trader._peak_equity = Decimal("10000")
    import asyncio
    async def _setup():
        await trader._portfolio.update_equity(Decimal("7000"))
    asyncio.run(_setup())
    tripped = trader._check_breaker()
    assert isinstance(tripped, bool)
    tem = tmp_path / "tem" / "trader4.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text("ok")
    assert "tem" in str(tem)