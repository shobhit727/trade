from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from cryptobot.config import settings
from cryptobot.core.events import (
    Event, EventType, OrderEvent, PositionEvent, PnLEvent,
    OrderStatus, PositionSide, OrderSide, OrderType, TimeInForce
)

try:
    import sqlite3
except ModuleNotFoundError:
    import logging
    logging.getLogger(__name__).warning("sqlite3 unavailable; state persistence disabled")
    sqlite3 = None


@dataclass
class Order:
    order_id: str = ""
    client_order_id: str = ""
    symbol: str = ""
    side: OrderSide = OrderSide.BUY
    type: OrderType = OrderType.LIMIT
    quantity: Decimal = Decimal("0")
    price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    status: OrderStatus = OrderStatus.NEW
    filled_quantity: Decimal = Decimal("0")
    avg_fill_price: Optional[Decimal] = None
    commission: Decimal = Decimal("0")
    commission_asset: str = ""
    time_in_force: TimeInForce = TimeInForce.GTC
    reduce_only: bool = False
    position_side: PositionSide = PositionSide.BOTH
    strategy: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_event(self) -> OrderEvent:
        return OrderEvent(
            order_id=self.order_id,
            client_order_id=self.client_order_id,
            symbol=self.symbol,
            side=self.side,
            type=self.type,
            quantity=self.quantity,
            price=self.price,
            stop_price=self.stop_price,
            status=self.status,
            filled_quantity=self.filled_quantity,
            avg_fill_price=self.avg_fill_price,
            commission=self.commission,
            commission_asset=self.commission_asset,
            time_in_force=self.time_in_force,
            reduce_only=self.reduce_only,
            position_side=self.position_side,
            strategy=self.strategy,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "client_order_id": self.client_order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "type": self.type.value,
            "quantity": str(self.quantity),
            "price": str(self.price) if self.price else None,
            "stop_price": str(self.stop_price) if self.stop_price else None,
            "status": self.status.value,
            "filled_quantity": str(self.filled_quantity),
            "avg_fill_price": str(self.avg_fill_price) if self.avg_fill_price else None,
            "commission": str(self.commission),
            "commission_asset": self.commission_asset,
            "time_in_force": self.time_in_force.value,
            "reduce_only": self.reduce_only,
            "position_side": self.position_side.value,
            "strategy": self.strategy,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class Position:
    symbol: str = ""
    side: PositionSide = PositionSide.LONG
    quantity: Decimal = Decimal("0")
    entry_price: Decimal = Decimal("0")
    mark_price: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    leverage: int = 1
    margin_type: str = "ISOLATED"
    isolated_margin: Decimal = Decimal("0")
    liquidation_price: Optional[Decimal] = None
    strategy: str = ""
    opened_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_event(self) -> PositionEvent:
        return PositionEvent(
            symbol=self.symbol,
            side=self.side,
            quantity=self.quantity,
            entry_price=self.entry_price,
            mark_price=self.mark_price,
            unrealized_pnl=self.unrealized_pnl,
            realized_pnl=self.realized_pnl,
            leverage=self.leverage,
            margin_type=self.margin_type,
            isolated_margin=self.isolated_margin,
            liquidation_price=self.liquidation_price,
            strategy=self.strategy,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": str(self.quantity),
            "entry_price": str(self.entry_price),
            "mark_price": str(self.mark_price),
            "unrealized_pnl": str(self.unrealized_pnl),
            "realized_pnl": str(self.realized_pnl),
            "leverage": self.leverage,
            "margin_type": self.margin_type,
            "isolated_margin": str(self.isolated_margin),
            "liquidation_price": str(self.liquidation_price) if self.liquidation_price else None,
            "strategy": self.strategy,
            "opened_at": self.opened_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class AccountState:
    total_equity: Decimal = Decimal("0")
    available_balance: Decimal = Decimal("0")
    used_margin: Decimal = Decimal("0")
    total_unrealized_pnl: Decimal = Decimal("0")
    total_realized_pnl: Decimal = Decimal("0")
    daily_pnl: Decimal = Decimal("0")
    max_drawdown: Decimal = Decimal("0")
    peak_equity: Decimal = Decimal("0")
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_event(self) -> PnLEvent:
        return PnLEvent(
            total_unrealized=self.total_unrealized_pnl,
            total_realized=self.total_realized_pnl,
            daily_pnl=self.daily_pnl,
            total_equity=self.total_equity,
            available_balance=self.available_balance,
            used_margin=self.used_margin,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_equity": str(self.total_equity),
            "available_balance": str(self.available_balance),
            "used_margin": str(self.used_margin),
            "total_unrealized_pnl": str(self.total_unrealized_pnl),
            "total_realized_pnl": str(self.total_realized_pnl),
            "daily_pnl": str(self.daily_pnl),
            "max_drawdown": str(self.max_drawdown),
            "peak_equity": str(self.peak_equity),
            "updated_at": self.updated_at.isoformat(),
        }


class StateManager:
    _instance: Optional[StateManager] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._orders: dict[str, Order] = {}
        self._positions: dict[str, Position] = {}
        self._account = AccountState()
        self._daily_pnl_start: Decimal = Decimal("0")
        self._db_path = Path(settings.database.name + ".db")
        if sqlite3 is not None:
            self._init_db()

    def _init_db(self):
        if sqlite3 is None:
            return
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    client_order_id TEXT,
                    symbol TEXT,
                    side TEXT,
                    type TEXT,
                    quantity TEXT,
                    price TEXT,
                    stop_price TEXT,
                    status TEXT,
                    filled_quantity TEXT,
                    avg_fill_price TEXT,
                    commission TEXT,
                    commission_asset TEXT,
                    time_in_force TEXT,
                    reduce_only INTEGER,
                    position_side TEXT,
                    strategy TEXT,
                    created_at TEXT,
                    updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS positions (
                    symbol TEXT PRIMARY KEY,
                    side TEXT,
                    quantity TEXT,
                    entry_price TEXT,
                    mark_price TEXT,
                    unrealized_pnl TEXT,
                    realized_pnl TEXT,
                    leverage INTEGER,
                    margin_type TEXT,
                    isolated_margin TEXT,
                    liquidation_price TEXT,
                    strategy TEXT,
                    opened_at TEXT,
                    updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS account_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    total_equity TEXT,
                    available_balance TEXT,
                    used_margin TEXT,
                    total_unrealized_pnl TEXT,
                    total_realized_pnl TEXT,
                    daily_pnl TEXT,
                    max_drawdown TEXT,
                    peak_equity TEXT,
                    updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    type TEXT,
                    timestamp TEXT,
                    source TEXT,
                    correlation_id TEXT,
                    payload TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
                CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);
            """)

    @contextmanager
    def _get_conn(self):
        if sqlite3 is None:
            raise RuntimeError("sqlite3 unavailable; StateManager persistence disabled")
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def load(self):
        if sqlite3 is None:
            return
        with self._get_conn() as conn:
            # Load orders
            for row in conn.execute("SELECT * FROM orders"):
                order = Order(
                    order_id=row["order_id"],
                    client_order_id=row["client_order_id"],
                    symbol=row["symbol"],
                    side=OrderSide(row["side"]),
                    type=OrderType(row["type"]),
                    quantity=Decimal(row["quantity"]),
                    price=Decimal(row["price"]) if row["price"] else None,
                    stop_price=Decimal(row["stop_price"]) if row["stop_price"] else None,
                    status=OrderStatus(row["status"]),
                    filled_quantity=Decimal(row["filled_quantity"]),
                    avg_fill_price=Decimal(row["avg_fill_price"]) if row["avg_fill_price"] else None,
                    commission=Decimal(row["commission"]),
                    commission_asset=row["commission_asset"],
                    time_in_force=TimeInForce(row["time_in_force"]),
                    reduce_only=bool(row["reduce_only"]),
                    position_side=PositionSide(row["position_side"]),
                    strategy=row["strategy"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                )
                self._orders[order.order_id] = order

            # Load positions
            for row in conn.execute("SELECT * FROM positions"):
                pos = Position(
                    symbol=row["symbol"],
                    side=PositionSide(row["side"]),
                    quantity=Decimal(row["quantity"]),
                    entry_price=Decimal(row["entry_price"]),
                    mark_price=Decimal(row["mark_price"]),
                    unrealized_pnl=Decimal(row["unrealized_pnl"]),
                    realized_pnl=Decimal(row["realized_pnl"]),
                    leverage=row["leverage"],
                    margin_type=row["margin_type"],
                    isolated_margin=Decimal(row["isolated_margin"]),
                    liquidation_price=Decimal(row["liquidation_price"]) if row["liquidation_price"] else None,
                    strategy=row["strategy"],
                    opened_at=datetime.fromisoformat(row["opened_at"]),
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                )
                self._positions[pos.symbol] = pos

            # Load account state
            row = conn.execute("SELECT * FROM account_state WHERE id = 1").fetchone()
            if row:
                self._account = AccountState(
                    total_equity=Decimal(row["total_equity"]),
                    available_balance=Decimal(row["available_balance"]),
                    used_margin=Decimal(row["used_margin"]),
                    total_unrealized_pnl=Decimal(row["total_unrealized_pnl"]),
                    total_realized_pnl=Decimal(row["total_realized_pnl"]),
                    daily_pnl=Decimal(row["daily_pnl"]),
                    max_drawdown=Decimal(row["max_drawdown"]),
                    peak_equity=Decimal(row["peak_equity"]),
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                )
                self._daily_pnl_start = self._account.total_equity - self._account.daily_pnl

    def save_order(self, order: Order):
        order.updated_at = datetime.utcnow()
        self._orders[order.order_id] = order
        if sqlite3 is None:
            return
        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO orders VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                order.order_id, order.client_order_id, order.symbol, order.side.value,
                order.type.value, str(order.quantity), str(order.price) if order.price else None,
                str(order.stop_price) if order.stop_price else None, order.status.value,
                str(order.filled_quantity), str(order.avg_fill_price) if order.avg_fill_price else None,
                str(order.commission), order.commission_asset, order.time_in_force.value,
                int(order.reduce_only), order.position_side.value, order.strategy,
                order.created_at.isoformat(), order.updated_at.isoformat()
            ))

    def save_position(self, position: Position):
        position.updated_at = datetime.utcnow()
        self._positions[position.symbol] = position
        if sqlite3 is None:
            return
        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO positions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                position.symbol, position.side.value, str(position.quantity),
                str(position.entry_price), str(position.mark_price),
                str(position.unrealized_pnl), str(position.realized_pnl),
                position.leverage, position.margin_type, str(position.isolated_margin),
                str(position.liquidation_price) if position.liquidation_price else None,
                position.strategy, position.opened_at.isoformat(),
                position.updated_at.isoformat()
            ))

    def save_account(self):
        self._account.updated_at = datetime.utcnow()
        if sqlite3 is None:
            return
        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO account_state (id, total_equity, available_balance, used_margin,
                    total_unrealized_pnl, total_realized_pnl, daily_pnl, max_drawdown, peak_equity, updated_at)
                VALUES (1,?,?,?,?,?,?,?,?,?)
            """, (
                str(self._account.total_equity), str(self._account.available_balance),
                str(self._account.used_margin), str(self._account.total_unrealized_pnl),
                str(self._account.total_realized_pnl), str(self._account.daily_pnl),
                str(self._account.max_drawdown), str(self._account.peak_equity),
                self._account.updated_at.isoformat()
            ))

    def save_event(self, event: Event):
        if sqlite3 is None:
            return
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO events VALUES (?,?,?,?,?,?)
            """, (
                event.id, event.type.value, event.timestamp.isoformat(),
                event.source, event.correlation_id, json.dumps(event.payload)
            ))

    def get_order(self, order_id: str) -> Optional[Order]:
        return self._orders.get(order_id)

    def get_orders(self, symbol: str = "", strategy: str = "") -> list[Order]:
        orders = list(self._orders.values())
        if symbol:
            orders = [o for o in orders if o.symbol == symbol]
        if strategy:
            orders = [o for o in orders if o.strategy == strategy]
        return orders

    def get_open_orders(self, symbol: str = "") -> list[Order]:
        orders = [o for o in self._orders.values()
                  if o.status in (OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED, OrderStatus.PENDING_CANCEL)]
        if symbol:
            orders = [o for o in orders if o.symbol == symbol]
        return orders

    def get_position(self, symbol: str) -> Optional[Position]:
        return self._positions.get(symbol)

    def get_positions(self, strategy: str = "") -> list[Position]:
        positions = list(self._positions.values())
        if strategy:
            positions = [p for p in positions if p.strategy == strategy]
        return positions

    def get_account(self) -> AccountState:
        return self._account

    def update_account_equity(self, equity: Decimal):
        self._account.total_equity = equity
        if equity > self._account.peak_equity:
            self._account.peak_equity = equity
        drawdown = (self._account.peak_equity - equity) / self._account.peak_equity if self._account.peak_equity > 0 else Decimal("0")
        if drawdown > self._account.max_drawdown:
            self._account.max_drawdown = drawdown
        self._account.daily_pnl = equity - self._daily_pnl_start
        self.save_account()

    def reset_daily_pnl(self):
        self._daily_pnl_start = self._account.total_equity
        self._account.daily_pnl = Decimal("0")
        self.save_account()

    def get_daily_pnl_pct(self) -> float:
        if self._daily_pnl_start > 0:
            return float(self._account.daily_pnl / self._daily_pnl_start)
        return 0.0

    def get_drawdown_pct(self) -> float:
        return float(self._account.max_drawdown)


state_manager = StateManager()
