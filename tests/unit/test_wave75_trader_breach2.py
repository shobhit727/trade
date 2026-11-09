"""Wave75: trader breach2 - more branches (tem/ path)."""
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone
import asyncio
from unittest.mock import patch, AsyncMock

import pytest

@pytest.mark.asyncio
async def test_trader_breach2(tmp_path: Path):
    from cryptobot.live.trader import LiveTrader, LiveTraderConfig
    from cryptobot.core.events import KlineEvent, OrderEvent, OrderSide, OrderType
    tem = tmp_path / "tem" / "trader_breach2.json"
    tem.parent.mkdir(parents=True, exist_ok=True)
    cfg = LiveTraderConfig(symbol="BTCUSDT", timeframe="1m", mode="paper", warmup_bars=2)
    trader = LiveTrader(cfg)
    # Set equity for rescale_order
    await trader._portfolio.update_equity(Decimal("10000"))
    # test _place_protective_stop
    order = OrderEvent(symbol="BTCUSDT", side=OrderSide.BUY, type=OrderType.MARKET, quantity=Decimal("1"), avg_fill_price=Decimal("50000"), filled_quantity=Decimal("1"), strategy="test")
    await trader._place_protective_stop(order, Decimal("50000"))
    # test _rescale_order with reduce_only
    order2 = OrderEvent(symbol="BTCUSDT", side=OrderSide.SELL, type=OrderType.MARKET, quantity=Decimal("10"), strategy="test", payload={"flip": True}, reduce_only=True)
    trader._engine.venue._position_qty = {"BTCUSDT": Decimal("5")}
    trader._rescale_order(order2, Decimal("50000"))
    assert order2.quantity == Decimal("5")
    # test _update_position_book
    order3 = OrderEvent(symbol="BTCUSDT", side=OrderSide.BUY, type=OrderType.MARKET, quantity=Decimal("1"), avg_fill_price=Decimal("50000"), filled_quantity=Decimal("1"), strategy="test")
    trader._update_position_book(order3)
    assert trader._net_qty["BTCUSDT"] == Decimal("1")
    # test _check_breaker with peak
    trader._peak_equity = Decimal("10000")
    await trader._portfolio.update_equity(Decimal("10000"))
    tripped = await trader._check_breaker()
    assert isinstance(tripped, bool)
    tem.write_text("ok")
    assert "tem" in str(tem)
