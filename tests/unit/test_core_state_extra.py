"""Core state extra: StateManager, Order, Position (tem/ path)."""

from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone

def test_state_manager_order_position(tmp_path: Path):
    from cryptobot.core.state import StateManager, Order, Position
    from cryptobot.core.events import OrderSide, OrderStatus, OrderType, PositionSide
    sm = StateManager()
    sm._positions.clear()
    sm._orders.clear()
    # create order
    order = Order(symbol="BTCUSDT", side=OrderSide.BUY, type=OrderType.MARKET, quantity=Decimal("1"), price=Decimal("50000"), status=OrderStatus.NEW)
    sm.save_order(order)
    assert len(sm.get_orders()) >= 1
    # create position
    pos = Position(symbol="BTCUSDT", side=PositionSide.LONG, quantity=Decimal("1"), entry_price=Decimal("50000"), mark_price=Decimal("51000"), strategy="test")
    sm.save_position(pos)
    assert len(sm.get_positions()) >= 1
    # tem artifact
    p = tmp_path / "tem" / "state.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("ok")
    assert "tem" in str(p)

def test_portfolio_extra(tmp_path: Path):
    from cryptobot.core.portfolio import PortfolioManager, PortfolioMode
    import asyncio
    pm = PortfolioManager(PortfolioMode.BACKTEST)
    async def _run():
        await pm.update_equity(Decimal("10000"))
        await pm.update_equity(Decimal("10500"))
        assert pm.get_state().total_equity == Decimal("10500")
        assert len(pm.get_equity_curve()) >= 2
    asyncio.run(_run())
    p = tmp_path / "tem" / "portfolio.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("ok")
    assert p.exists()
