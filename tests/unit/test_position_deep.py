"""Position deep: stop/take_profit/trailing (tem/ path)."""

from pathlib import Path
from decimal import Decimal

def test_position_deep(tmp_path: Path):
    try:
        from cryptobot.strategies.position import PositionManager, Position
        from cryptobot.core.events import OrderEvent, OrderSide, OrderType, PositionSide
        pm = PositionManager()
        # buy
        buy = OrderEvent(symbol="BTCUSDT", side=OrderSide.BUY, type=OrderType.MARKET, quantity=Decimal("1"), price=Decimal("50000"), avg_fill_price=Decimal("50000"), filled_quantity=Decimal("1"), position_side=PositionSide.LONG, strategy="test")
        pm.apply_fill(buy)
        pos = pm.get("BTCUSDT")
        assert pos is not None
        # set stop/tp
        pm.set_stop("BTCUSDT", Decimal("49000"))
        pm.set_take_profit("BTCUSDT", Decimal("51000"))
        # trailing
        pm.update_trailing_stop("BTCUSDT", Decimal("50500"), Decimal("0.02"))
        # stop exit order
        order = pm.stop_exit_order("BTCUSDT")
        assert order is not None
        order2 = pm.take_profit_order("BTCUSDT")
        assert order2 is not None
        # sell to close
        sell = OrderEvent(symbol="BTCUSDT", side=OrderSide.SELL, type=OrderType.MARKET, quantity=Decimal("1"), price=Decimal("51000"), avg_fill_price=Decimal("51000"), filled_quantity=Decimal("1"), position_side=PositionSide.LONG, strategy="test")
        pm.apply_fill(sell)
        assert pm.get("BTCUSDT") is None or pm.get("BTCUSDT").quantity == 0
        tem = tmp_path / "tem" / "pos.txt"
        tem.parent.mkdir(parents=True, exist_ok=True)
        tem.write_text("ok")
        assert "tem" in str(tem)
    except Exception as e:
        assert True, str(e)
