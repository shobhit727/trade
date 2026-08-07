"""Tests for strategies/position.py (PositionManager primitives)."""

from __future__ import annotations

from decimal import Decimal

from cryptobot.core.events import OrderEvent, OrderSide, OrderType, PositionSide
from cryptobot.strategies.position import PositionManager


def _fill(
    side: OrderSide,
    qty: str,
    price: str,
    pos_side: PositionSide = PositionSide.BOTH,
    symbol: str = "BTCUSDT",
) -> OrderEvent:
    return OrderEvent(
        symbol=symbol,
        side=side,
        type=OrderType.MARKET,
        quantity=Decimal(qty),
        avg_fill_price=Decimal(price),
        filled_quantity=Decimal(qty),
        position_side=pos_side,
        strategy="test",
    )


def test_entry_long():
    pm = PositionManager()
    pm.apply_fill(_fill(OrderSide.BUY, "1", "100", PositionSide.LONG))
    pos = pm.get("BTCUSDT")
    assert pos is not None and pos.quantity == Decimal("1")
    assert pos.avg_entry == Decimal("100")
    assert pos.side is PositionSide.LONG


def test_entry_short():
    pm = PositionManager()
    pm.apply_fill(_fill(OrderSide.SELL, "2", "50", PositionSide.SHORT))
    pos = pm.get("BTCUSDT")
    assert pos is not None and pos.side is PositionSide.SHORT
    assert pos.quantity == Decimal("2")


def test_scale_in_average_entry():
    pm = PositionManager()
    pm.apply_fill(_fill(OrderSide.BUY, "1", "100", PositionSide.LONG))
    pm.apply_fill(_fill(OrderSide.BUY, "1", "200", PositionSide.LONG))
    pos = pm.get("BTCUSDT")
    assert pos.quantity == Decimal("2")
    assert pos.avg_entry == Decimal("150")


def test_scale_out_long():
    pm = PositionManager()
    pm.apply_fill(_fill(OrderSide.BUY, "2", "100", PositionSide.LONG))
    pm.apply_fill(_fill(OrderSide.SELL, "1", "110", PositionSide.LONG))
    pos = pm.get("BTCUSDT")
    assert pos.quantity == Decimal("1")
    assert pos.avg_entry == Decimal("100")


def test_scale_in_short():
    pm = PositionManager()
    pm.apply_fill(_fill(OrderSide.SELL, "1", "100", PositionSide.SHORT))
    pm.apply_fill(_fill(OrderSide.SELL, "1", "110", PositionSide.SHORT))
    pos = pm.get("BTCUSDT")
    assert pos.quantity == Decimal("2")
    assert pos.avg_entry == Decimal("105")


def test_full_close_zeroes_position():
    pm = PositionManager()
    pm.apply_fill(_fill(OrderSide.BUY, "1", "100", PositionSide.LONG))
    pm.apply_fill(_fill(OrderSide.SELL, "1", "105", PositionSide.LONG))
    pos = pm.get("BTCUSDT")
    assert pos.quantity == Decimal("0")
    assert pos.avg_entry == Decimal("0")
    assert pm.all() == []


def test_trailing_stop_ratchets_long():
    pm = PositionManager()
    pm.apply_fill(_fill(OrderSide.BUY, "1", "100", PositionSide.LONG))
    s1 = pm.update_trailing_stop("BTCUSDT", Decimal("110"), Decimal("0.05"))
    assert s1 == Decimal("104.5")
    s2 = pm.update_trailing_stop("BTCUSDT", Decimal("100"), Decimal("0.05"))
    assert s2 is None  # stop does not ratchet down
    s3 = pm.update_trailing_stop("BTCUSDT", Decimal("120"), Decimal("0.05"))
    assert s3 == Decimal("114")
    assert pm.get("BTCUSDT").stop_price == Decimal("114")


def test_trailing_stop_short_ratchets_down():
    pm = PositionManager()
    pm.apply_fill(_fill(OrderSide.SELL, "1", "100", PositionSide.SHORT))
    s1 = pm.update_trailing_stop("BTCUSDT", Decimal("90"), Decimal("0.05"))
    assert s1 == Decimal("94.5")
    s2 = pm.update_trailing_stop("BTCUSDT", Decimal("95"), Decimal("0.05"))
    assert s2 is None
    s3 = pm.update_trailing_stop("BTCUSDT", Decimal("80"), Decimal("0.05"))
    assert s3 == Decimal("84")


def test_stop_exit_order_long():
    pm = PositionManager()
    pm.apply_fill(_fill(OrderSide.BUY, "1", "100", PositionSide.LONG))
    pm.set_stop("BTCUSDT", Decimal("95"))
    order = pm.stop_exit_order("BTCUSDT")
    assert order is not None
    assert order.side is OrderSide.SELL
    assert order.type is OrderType.STOP_LOSS
    assert order.reduce_only is True
    assert order.quantity == Decimal("1")


def test_take_profit_order_short():
    pm = PositionManager()
    pm.apply_fill(_fill(OrderSide.SELL, "1", "100", PositionSide.SHORT))
    pm.set_take_profit("BTCUSDT", Decimal("80"))
    order = pm.take_profit_order("BTCUSDT")
    assert order is not None
    assert order.side is OrderSide.BUY
    assert order.type is OrderType.TAKE_PROFIT
    assert order.price == Decimal("80")


def test_no_exit_without_stop():
    pm = PositionManager()
    pm.apply_fill(_fill(OrderSide.BUY, "1", "100", PositionSide.LONG))
    assert pm.stop_exit_order("BTCUSDT") is None
    assert pm.take_profit_order("BTCUSDT") is None


def test_ignore_empty_fill():
    pm = PositionManager()
    pm.apply_fill(_fill(OrderSide.BUY, "0", "100", PositionSide.LONG))
    assert pm.all() == []
