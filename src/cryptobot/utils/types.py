from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, TypedDict


@dataclass
class Candle:
    """OHLCV candle data."""
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    trades: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Candle:
        """Create Candle from dictionary."""
        return cls(
            timestamp=datetime.fromisoformat(data['timestamp']),
            open=Decimal(str(data['open'])),
            high=Decimal(str(data['high'])),
            low=Decimal(str(data['low'])),
            close=Decimal(str(data['close'])),
            volume=Decimal(str(data['volume'])),
            trades=data.get('trades', 0),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert Candle to dictionary."""
        return {
            'timestamp': self.timestamp.isoformat(),
            'open': str(self.open),
            'high': str(self.high),
            'low': str(self.low),
            'close': str(self.close),
            'volume': str(self.volume),
            'trades': self.trades,
        }

    @property
    def body(self) -> Decimal:
        """Get candle body."""
        return abs(self.close - self.open)

    @property
    def upper_shadow(self) -> Decimal:
        """Get upper shadow."""
        return self.high - max(self.open, self.close)

    @property
    def lower_shadow(self) -> Decimal:
        """Get lower shadow."""
        return min(self.open, self.close) - self.low

    @property
    def is_bullish(self) -> bool:
        """Check if candle is bullish."""
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        """Check if candle is bearish."""
        return self.close < self.open


@dataclass
class OrderBookLevel:
    """Single order book level."""
    price: Decimal
    quantity: Decimal
    total: Decimal = field(init=False)

    def __post_init__(self):
        self.total = self.price * self.quantity

    @classmethod
    def from_tuple(cls, data: tuple) -> OrderBookLevel:
        """Create from tuple (price, quantity)."""
        return cls(
            price=Decimal(str(data[0])),
            quantity=Decimal(str(data[1])),
        )


@dataclass
class OrderBook:
    """Order book with bids and asks."""
    symbol: str
    timestamp: datetime
    bids: list[OrderBookLevel] = field(default_factory=list)
    asks: list[OrderBookLevel] = field(default_factory=list)
    sequence: int = 0

    @property
    def best_bid(self) -> Decimal | None:
        """Get best bid price."""
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Decimal | None:
        """Get best ask price."""
        return self.asks[0].price if self.asks else None

    @property
    def spread(self) -> Decimal | None:
        """Get bid-ask spread."""
        if self.bids and self.asks:
            return self.asks[0].price - self.bids[0].price
        return None

    @property
    def mid_price(self) -> Decimal | None:
        """Get mid price."""
        if self.bids and self.asks:
            return (self.bids[0].price + self.asks[0].price) / 2
        return None

    def depth(self, levels: int = 10) -> dict[str, Any]:
        """Get order book depth."""
        return {
            'bids': [
                {'price': str(level.price), 'quantity': str(level.quantity)}
                for level in self.bids[:levels]
            ],
            'asks': [
                {'price': str(level.price), 'quantity': str(level.quantity)}
                for level in self.asks[:levels]
            ],
        }

    def imbalance(self) -> Decimal | None:
        """Get order book imbalance."""
        if not self.bids or not self.asks:
            return None

        bid_volume = sum(level.quantity for level in self.bids[:10])
        ask_volume = sum(level.quantity for level in self.asks[:10])

        total = bid_volume + ask_volume
        if total == 0:
            return Decimal('0')

        return (bid_volume - ask_volume) / total


@dataclass
class Trade:
    """Single trade execution."""
    symbol: str
    price: Decimal
    quantity: Decimal
    side: str  # 'buy' or 'sell'
    timestamp: datetime
    trade_id: str = ''
    is_maker: bool = False

    @property
    def value(self) -> Decimal:
        """Get trade value in quote currency."""
        return self.price * self.quantity




class TickData(TypedDict, total=False):
    """Tick/Ticker payload."""
    symbol: str
    timestamp: str
    bid: str
    ask: str
    last: str
    bid_qty: str
    ask_qty: str
    volume_24h: str


class OHLCVBar(TypedDict, total=False):
    """OHLCV bar payload."""
    symbol: str
    timeframe: str
    open_time: str
    close_time: str
    open: str
    high: str
    low: str
    close: str
    volume: str
    trades: int
    is_closed: bool


class PerformanceMetrics(TypedDict, total=False):
    """Performance metrics summary."""
    total_return: float
    annualized_return: float
    volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    max_drawdown_pct: float
    win_rate: float
    profit_factor: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    period_start: str
    period_end: str
