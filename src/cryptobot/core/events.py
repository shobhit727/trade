from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import uuid4


def _utcnow() -> datetime:
    return datetime.now(UTC)


class EventType(StrEnum):
    # Market Data
    TICKER = "ticker"
    ORDERBOOK = "orderbook"
    TRADE = "trade"
    KLINE = "kline"
    FUNDING_RATE = "funding_rate"

    # Signals
    SIGNAL = "signal"
    SIGNAL_ENTRY = "signal_entry"
    SIGNAL_EXIT = "signal_exit"
    SIGNAL_SCALE_IN = "signal_scale_in"
    SIGNAL_SCALE_OUT = "signal_scale_out"
    SIGNAL_HEDGE = "signal_hedge"

    # Orders
    ORDER_NEW = "order_new"
    ORDER_ACK = "order_ack"
    ORDER_PARTIAL = "order_partial"
    ORDER_FILLED = "order_filled"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_REJECTED = "order_rejected"
    ORDER_EXPIRED = "order_expired"

    # Positions
    POSITION_OPEN = "position_open"
    POSITION_UPDATE = "position_update"
    POSITION_CLOSE = "position_close"
    POSITION_LIQUIDATED = "position_liquidated"

    # P&L
    PNL_UPDATE = "pnl_update"
    PNL_REALIZED = "pnl_realized"
    PNL_UNREALIZED = "pnl_unrealized"

    # Risk
    RISK_CHECK = "risk_check"
    RISK_APPROVED = "risk_approved"
    RISK_REJECTED = "risk_rejected"
    RISK_WARNING = "risk_warning"
    KILL_SWITCH = "kill_switch"

    # System
    HEARTBEAT = "heartbeat"
    STARTUP = "startup"
    SHUTDOWN = "shutdown"
    ERROR = "error"
    CONFIG_CHANGE = "config_change"

    ALL = "*"


class SignalSide(StrEnum):
    BUY = "buy"
    SELL = "sell"
    CLOSE_LONG = "close_long"
    CLOSE_SHORT = "close_short"


class SignalStrength(StrEnum):
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    VERY_STRONG = "very_strong"


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_LIMIT = "STOP_LOSS_LIMIT"
    TAKE_PROFIT = "TAKE_PROFIT"
    TAKE_PROFIT_LIMIT = "TAKE_PROFIT_LIMIT"
    LIMIT_MAKER = "LIMIT_MAKER"


class OrderStatus(StrEnum):
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    PENDING_CANCEL = "PENDING_CANCEL"


class TimeInForce(StrEnum):
    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"
    GTX = "GTX"


class PositionSide(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    BOTH = "BOTH"


@dataclass
class Event:
    id: str = field(default_factory=lambda: str(uuid4()))
    type: EventType = EventType.ERROR
    timestamp: datetime = field(default_factory=_utcnow)
    source: str = ""
    correlation_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "correlation_id": self.correlation_id,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Event:
        return cls(
            id=data.get("id", str(uuid4())),
            type=EventType(data["type"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id", ""),
            payload=data.get("payload", {}),
        )


@dataclass
class TickerEvent(Event):
    symbol: str = ""
    price: Decimal = Decimal("0")
    bid: Decimal = Decimal("0")
    ask: Decimal = Decimal("0")
    bid_qty: Decimal = Decimal("0")
    ask_qty: Decimal = Decimal("0")
    high_24h: Decimal = Decimal("0")
    low_24h: Decimal = Decimal("0")
    volume_24h: Decimal = Decimal("0")
    change_24h: float = 0.0

    def __post_init__(self):
        self.type = EventType.TICKER
        self.payload = {
            "symbol": self.symbol,
            "price": str(self.price),
            "bid": str(self.bid),
            "ask": str(self.ask),
            "bid_qty": str(self.bid_qty),
            "ask_qty": str(self.ask_qty),
            "high_24h": str(self.high_24h),
            "low_24h": str(self.low_24h),
            "volume_24h": str(self.volume_24h),
            "change_24h": self.change_24h,
        }


@dataclass
class OrderBookEvent(Event):
    symbol: str = ""
    bids: list[tuple[Decimal, Decimal]] = field(default_factory=list)
    asks: list[tuple[Decimal, Decimal]] = field(default_factory=list)
    sequence: int = 0
    timestamp: datetime = field(default_factory=_utcnow)

    def __post_init__(self):
        self.type = EventType.ORDERBOOK
        self.payload = {
            "symbol": self.symbol,
            "bids": [[str(p), str(q)] for p, q in self.bids],
            "asks": [[str(p), str(q)] for p, q in self.asks],
            "sequence": self.sequence,
        }

    @property
    def best_bid(self) -> Decimal:
        return self.bids[0][0] if self.bids else Decimal("0")

    @property
    def best_ask(self) -> Decimal:
        return self.asks[0][0] if self.asks else Decimal("0")

    @property
    def spread(self) -> Decimal:
        if self.bids and self.asks:
            return self.asks[0][0] - self.bids[0][0]
        return Decimal("0")

    @property
    def mid_price(self) -> Decimal:
        if self.bids and self.asks:
            return (self.bids[0][0] + self.asks[0][0]) / 2
        return Decimal("0")


@dataclass
class TradeEvent(Event):
    symbol: str = ""
    trade_id: str = ""
    price: Decimal = Decimal("0")
    quantity: Decimal = Decimal("0")
    side: OrderSide = OrderSide.BUY
    is_maker: bool = False
    timestamp: datetime = field(default_factory=_utcnow)

    def __post_init__(self):
        self.type = EventType.TRADE
        self.payload = {
            "symbol": self.symbol,
            "trade_id": self.trade_id,
            "price": str(self.price),
            "quantity": str(self.quantity),
            "side": self.side.value,
            "is_maker": self.is_maker,
        }


@dataclass
class KlineEvent(Event):
    symbol: str = ""
    interval: str = ""
    open_time: datetime = field(default_factory=_utcnow)
    close_time: datetime = field(default_factory=_utcnow)
    open_price: Decimal = Decimal("0")
    high_price: Decimal = Decimal("0")
    low_price: Decimal = Decimal("0")
    close_price: Decimal = Decimal("0")
    volume: Decimal = Decimal("0")
    trades: int = 0
    is_closed: bool = False

    def __post_init__(self):
        self.type = EventType.KLINE
        self.payload = {
            "symbol": self.symbol,
            "interval": self.interval,
            "open_time": self.open_time.isoformat(),
            "close_time": self.close_time.isoformat(),
            "open": str(self.open_price),
            "high": str(self.high_price),
            "low": str(self.low_price),
            "close": str(self.close_price),
            "volume": str(self.volume),
            "trades": self.trades,
            "is_closed": self.is_closed,
        }


@dataclass
class FundingRateEvent(Event):
    symbol: str = ""
    funding_rate: float = 0.0
    mark_price: Decimal = Decimal("0")
    index_price: Decimal = Decimal("0")
    next_funding_time: datetime = field(default_factory=_utcnow)

    def __post_init__(self):
        self.type = EventType.FUNDING_RATE
        self.payload = {
            "symbol": self.symbol,
            "funding_rate": self.funding_rate,
            "mark_price": str(self.mark_price),
            "index_price": str(self.index_price),
            "next_funding_time": self.next_funding_time.isoformat(),
        }


@dataclass
class SignalEvent(Event):
    strategy: str = ""
    symbol: str = ""
    side: SignalSide = SignalSide.BUY
    strength: SignalStrength = SignalStrength.MODERATE
    price: Decimal = Decimal("0")
    quantity: Decimal | None = None
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    expires_at: datetime | None = None

    def __post_init__(self):
        if self.type not in (
            EventType.SIGNAL, EventType.SIGNAL_ENTRY, EventType.SIGNAL_EXIT,
            EventType.SIGNAL_SCALE_IN, EventType.SIGNAL_SCALE_OUT, EventType.SIGNAL_HEDGE
        ):
            self.type = EventType.SIGNAL
        self.payload = {
            "strategy": self.strategy,
            "symbol": self.symbol,
            "side": self.side.value,
            "strength": self.strength.value,
            "price": str(self.price),
            "quantity": str(self.quantity) if self.quantity else None,
            "stop_loss": str(self.stop_loss) if self.stop_loss else None,
            "take_profit": str(self.take_profit) if self.take_profit else None,
            "metadata": self.metadata,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


@dataclass
class OrderEvent(Event):
    order_id: str = ""
    client_order_id: str = ""
    symbol: str = ""
    side: OrderSide = OrderSide.BUY
    type: OrderType = OrderType.LIMIT
    quantity: Decimal = Decimal("0")
    price: Decimal | None = None
    stop_price: Decimal | None = None
    status: OrderStatus = OrderStatus.NEW
    filled_quantity: Decimal = Decimal("0")
    avg_fill_price: Decimal | None = None
    commission: Decimal = Decimal("0")
    commission_asset: str = ""
    time_in_force: TimeInForce = TimeInForce.GTC
    reduce_only: bool = False
    position_side: PositionSide = PositionSide.BOTH
    strategy: str = ""

    def __post_init__(self):
        self.payload = {
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
        }

    def to_dict(self) -> dict[str, Any]:
        return {**super().to_dict(), **self.payload}


@dataclass
class PositionEvent(Event):
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
    liquidation_price: Decimal | None = None
    strategy: str = ""

    def __post_init__(self):
        self.payload = {
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
        }


@dataclass
class PnLEvent(Event):
    total_unrealized: Decimal = Decimal("0")
    total_realized: Decimal = Decimal("0")
    daily_pnl: Decimal = Decimal("0")
    total_equity: Decimal = Decimal("0")
    available_balance: Decimal = Decimal("0")
    used_margin: Decimal = Decimal("0")
    positions: dict[str, dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self):
        self.type = EventType.PNL_UPDATE
        self.payload = {
            "total_unrealized": str(self.total_unrealized),
            "total_realized": str(self.total_realized),
            "daily_pnl": str(self.daily_pnl),
            "total_equity": str(self.total_equity),
            "available_balance": str(self.available_balance),
            "used_margin": str(self.used_margin),
            "positions": self.positions,
        }


@dataclass
class RiskEvent(Event):
    check_type: str = ""
    passed: bool = True
    message: str = ""
    current_value: float | None = None
    limit_value: float | None = None
    symbol: str = ""
    strategy: str = ""

    def __post_init__(self):
        if not self.passed:
            self.type = EventType.RISK_REJECTED
        else:
            self.type = EventType.RISK_APPROVED
        self.payload = {
            "check_type": self.check_type,
            "passed": self.passed,
            "message": self.message,
            "current_value": self.current_value,
            "limit_value": self.limit_value,
            "symbol": self.symbol,
            "strategy": self.strategy,
        }


@dataclass
class KillSwitchEvent(Event):
    triggered: bool = True
    reason: str = ""
    daily_loss_pct: float = 0.0
    max_allowed_pct: float = 0.0

    def __post_init__(self):
        self.type = EventType.KILL_SWITCH
        self.payload = {
            "triggered": self.triggered,
            "reason": self.reason,
            "daily_loss_pct": self.daily_loss_pct,
            "max_allowed_pct": self.max_allowed_pct,
        }


@dataclass
class HeartbeatEvent(Event):
    component: str = ""
    status: str = "healthy"
    metrics: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.type = EventType.HEARTBEAT
        self.payload = {
            "component": self.component,
            "status": self.status,
            "metrics": self.metrics,
        }


@dataclass
class ErrorEvent(Event):
    component: str = ""
    error_type: str = ""
    message: str = ""
    stack_trace: str | None = None
    severity: str = "error"
    recoverable: bool = True

    def __post_init__(self):
        self.type = EventType.ERROR
        self.payload = {
            "component": self.component,
            "error_type": self.error_type,
            "message": self.message,
            "stack_trace": self.stack_trace,
            "severity": self.severity,
            "recoverable": self.recoverable,
        }


def create_event(event_type: EventType, **kwargs) -> Event:
    event_map = {
        EventType.TICKER: TickerEvent,
        EventType.ORDERBOOK: OrderBookEvent,
        EventType.TRADE: TradeEvent,
        EventType.KLINE: KlineEvent,
        EventType.FUNDING_RATE: FundingRateEvent,
        EventType.SIGNAL: SignalEvent,
        EventType.SIGNAL_ENTRY: SignalEvent,
        EventType.SIGNAL_EXIT: SignalEvent,
        EventType.SIGNAL_SCALE_IN: SignalEvent,
        EventType.SIGNAL_SCALE_OUT: SignalEvent,
        EventType.SIGNAL_HEDGE: SignalEvent,
        EventType.ORDER_NEW: OrderEvent,
        EventType.ORDER_ACK: OrderEvent,
        EventType.ORDER_PARTIAL: OrderEvent,
        EventType.ORDER_FILLED: OrderEvent,
        EventType.ORDER_CANCELLED: OrderEvent,
        EventType.ORDER_REJECTED: OrderEvent,
        EventType.ORDER_EXPIRED: OrderEvent,
        EventType.POSITION_OPEN: PositionEvent,
        EventType.POSITION_UPDATE: PositionEvent,
        EventType.POSITION_CLOSE: PositionEvent,
        EventType.POSITION_LIQUIDATED: PositionEvent,
        EventType.PNL_UPDATE: PnLEvent,
        EventType.PNL_REALIZED: PnLEvent,
        EventType.PNL_UNREALIZED: PnLEvent,
        EventType.RISK_CHECK: RiskEvent,
        EventType.RISK_APPROVED: RiskEvent,
        EventType.RISK_REJECTED: RiskEvent,
        EventType.RISK_WARNING: RiskEvent,
        EventType.KILL_SWITCH: KillSwitchEvent,
        EventType.HEARTBEAT: HeartbeatEvent,
        EventType.ERROR: ErrorEvent,
    }
    cls = event_map.get(event_type)
    if cls is None:
        raise ValueError(f"No event class registered for EventType {event_type!r}")
    return cls(type=event_type, **kwargs)
