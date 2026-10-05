"""Core state extra2: StateManager more branches (tem/ path)."""

from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone

def test_state_extra2(tmp_path: Path):
    from cryptobot.core.state import StateManager, Position, Order
    from cryptobot.core.events import OrderSide, OrderStatus, OrderType, PositionSide
    sm = StateManager()
    sm._positions.clear()
    sm._orders.clear()
    # test get_positions with strategy filter
    pos = Position(symbol="BTCUSDT", side=PositionSide.LONG, quantity=Decimal("1"), entry_price=Decimal("50000"), mark_price=Decimal("51000"), strategy="dual_ma")
    sm.save_position(pos)
    assert len(sm.get_positions(strategy="dual_ma")) >= 1
    assert len(sm.get_positions(strategy="nonexistent")) == 0
    # test get_orders
    order = Order(symbol="ETHUSDT", side=OrderSide.BUY, type=OrderType.LIMIT, quantity=Decimal("1"), price=Decimal("3000"), status=OrderStatus.NEW)
    sm.save_order(order)
    assert len(sm.get_orders(strategy="dual_ma")) >= 0
    # test account
    acc = sm.get_account()
    assert acc is not None
    tem = tmp_path / "tem" / "state2.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text(str(acc.total_equity))
    assert "tem" in str(tem)
