from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from cryptobot.core.state import AccountState, Position, StateManager


def test_state_manager_singleton():
    StateManager._instance = None
    a = StateManager()
    b = StateManager()
    assert a is b


def test_order_to_dict_contains_canonical_fields():
    from cryptobot.core.events import OrderEvent, OrderSide, OrderStatus, OrderType

    order = OrderEvent(
        order_id="o1", symbol="BTCUSDT", side=OrderSide.BUY, type=OrderType.LIMIT,
        quantity=Decimal("1"), price=Decimal("100"), status=OrderStatus.NEW,
        strategy="smoke",
    )
    d = order.to_dict()
    assert d["order_id"] == "o1"
    assert d["symbol"] == "BTCUSDT"
    assert d["side"] == "BUY"
    assert d["strategy"] == "smoke"


def test_position_to_event_roundtrip():
    from cryptobot.core.events import PositionSide

    pos = Position(symbol="BTCUSDT", side=PositionSide.LONG, quantity=Decimal("0.5"), entry_price=Decimal("100"))
    ev = pos.to_event()
    assert ev.symbol == "BTCUSDT"
    assert ev.side == PositionSide.LONG
    assert ev.strategy == pos.strategy


def test_account_state_to_event_uses_pnl_event():
    acc = AccountState(
        total_equity=Decimal("100"), available_balance=Decimal("80"),
        used_margin=Decimal("20"), total_unrealized_pnl=Decimal("0"),
        total_realized_pnl=Decimal("0"), daily_pnl=Decimal("0"),
        peak_equity=Decimal("100"), max_drawdown=Decimal("0"),
    )
    ev = acc.to_event()
    assert "total_unrealized" in ev.payload


def test_state_manager_methods_safe_when_sqlite_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("cryptobot.core.state.sqlite3", None)
    StateManager._instance = None
    sm = StateManager()
    sm.reset_daily_pnl()
    assert sm.get_account().total_equity == Decimal("0")
    sm.update_account_equity(Decimal("100"))
    assert sm.get_account().total_equity == Decimal("100")


def test_save_order_in_memory_path(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("cryptobot.core.state.sqlite3", None)
    StateManager._instance = None
    sm = StateManager()
    from cryptobot.core.state import Order
    from cryptobot.core.events import OrderSide, OrderStatus, OrderType

    order = Order(
        order_id="o2", symbol="BTCUSDT", side=OrderSide.BUY, type=OrderType.LIMIT,
        quantity=Decimal("1"), price=Decimal("100"), status=OrderStatus.NEW,
    )
    sm.save_order(order)
    assert sm.get_order("o2").symbol == "BTCUSDT"


def test_save_order_persists_to_sqlite(tmp_path: Path):
    """Regression for a latent bug: the sqlite INSERT referenced
    ``order.timestamp`` (which does not exist on Order) — now uses
    ``order.created_at`` and carries the correct number of columns (19)."""
    import sqlite3

    from cryptobot.core.state import Order
    from cryptobot.core.events import OrderSide, OrderStatus, OrderType

    db_file = tmp_path / "state.db"

    StateManager._instance = None
    sm = StateManager()
    sm._db_path = str(db_file)
    sm._init_db()

    order = Order(
        order_id="o-sql-1", symbol="BTCUSDT", side=OrderSide.BUY, type=OrderType.LIMIT,
        quantity=Decimal("1"), price=Decimal("100"), status=OrderStatus.NEW,
    )
    sm.save_order(order)

    conn = sqlite3.connect(str(db_file))
    row = conn.execute(
        "SELECT order_id, created_at, updated_at FROM orders WHERE order_id=?",
        ("o-sql-1",),
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[1] is not None and row[2] is not None


def test_position_serialization():
    from cryptobot.core.events import PositionSide

    pos = Position(symbol="ETHUSDT", side=PositionSide.SHORT, quantity=Decimal("2"), entry_price=Decimal("1500"))
    d = pos.to_dict()
    assert d["symbol"] == "ETHUSDT"
    assert d["side"] == "SHORT"
    assert d["entry_price"] == "1500"
