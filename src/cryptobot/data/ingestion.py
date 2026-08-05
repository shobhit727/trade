from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    import aiohttp
    import websockets

from cryptobot.core.bus import get_event_bus
from cryptobot.core.events import (
    Event,
    EventType,
    KlineEvent,
    OrderSide,
    TickerEvent,
    TradeEvent,
)
from cryptobot.utils.types import OrderBook, OrderBookLevel

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class OHLCV:
    """Single OHLCV bar."""
    symbol: str
    timeframe: str
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    trades: int = 0
    is_closed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "open_time": self.open_time.isoformat(),
            "close_time": self.close_time.isoformat(),
            "open": str(self.open),
            "high": str(self.high),
            "low": str(self.low),
            "close": str(self.close),
            "volume": str(self.volume),
            "trades": self.trades,
            "is_closed": self.is_closed,
        }


@dataclass
class Tick:
    """Ticker / top-of-book tick."""
    symbol: str
    timestamp: datetime
    bid: Decimal
    ask: Decimal
    last: Decimal
    bid_qty: Decimal = Decimal("0")
    ask_qty: Decimal = Decimal("0")
    volume_24h: Decimal = Decimal("0")

    @property
    def spread(self) -> Decimal:
        return self.ask - self.bid

    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / 2


@dataclass
class TradeData:
    """Single trade print."""
    symbol: str
    trade_id: str
    timestamp: datetime
    price: Decimal
    quantity: Decimal
    side: OrderSide
    is_maker: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "trade_id": self.trade_id,
            "timestamp": self.timestamp.isoformat(),
            "price": str(self.price),
            "quantity": str(self.quantity),
            "side": self.side.value,
            "is_maker": self.is_maker,
        }


@dataclass
class FundingRateData:
    """Funding rate data point."""
    symbol: str
    timestamp: datetime
    funding_rate: Decimal
    mark_price: Decimal
    index_price: Decimal
    next_funding_time: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "funding_rate": str(self.funding_rate),
            "mark_price": str(self.mark_price),
            "index_price": str(self.index_price),
            "next_funding_time": self.next_funding_time.isoformat(),
        }


@dataclass
class OrderBookSnapshot:
    """Complete order book snapshot."""
    symbol: str
    timestamp: datetime
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    sequence: int = 0

    @property
    def best_bid(self) -> Optional[OrderBookLevel]:
        return self.bids[0] if self.bids else None

    @property
    def best_ask(self) -> Optional[OrderBookLevel]:
        return self.asks[0] if self.asks else None

    @property
    def spread(self) -> Decimal:
        if self.best_bid and self.best_ask:
            return self.best_ask.price - self.best_bid.price
        return Decimal("0")

    @property
    def mid_price(self) -> Decimal:
        if self.best_bid and self.best_ask:
            return (self.best_bid.price + self.best_ask.price) / 2
        return Decimal("0")

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "bids": [{"price": str(l.price), "quantity": str(l.quantity)} for l in self.bids],
            "asks": [{"price": str(l.price), "quantity": str(l.quantity)} for l in self.asks],
            "sequence": self.sequence,
        }


@dataclass
class DataSourceConfig:
    """Configuration for a data source."""
    name: str
    venue: str
    symbols: list[str]
    timeframes: list[str]
    enabled: bool = True
    rate_limit: int = 1200
    api_key: str = ""
    api_secret: str = ""
    base_url: str = ""
    ws_url: str = ""
    # WebSocket reconnection
    ws_reconnect_interval: int = 5
    ws_max_reconnect_attempts: int = 10
    ws_ping_interval: int = 20
    ws_ping_timeout: int = 10


class DataIngestion(ABC):
    """Abstract base for data ingestion."""

    @abstractmethod
    async def start(self):
        pass

    @abstractmethod
    async def stop(self):
        pass

    @abstractmethod
    async def fetch_historical(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[dict]:
        pass

    @abstractmethod
    async def subscribe_realtime(self, symbol: str, timeframe: str):
        pass


class OrderBookReconstructor:
    """Reconstructs order book from trade and book ticker streams."""

    def __init__(self, symbol: str, max_depth: int = 100):
        self.symbol = symbol
        self.max_depth = max_depth
        self.bids: dict[Decimal, OrderBookLevel] = {}
        self.asks: dict[Decimal, OrderBookLevel] = {}
        self.last_update_id: int = 0
        self.last_update_time: float = 0
        self._lock = asyncio.Lock()

    async def apply_snapshot(self, bids: list[OrderBookLevel], asks: list[OrderBookLevel], update_id: int) -> None:
        """Apply a full order book snapshot."""
        async with self._lock:
            self.bids = {level.price: level for level in bids[:self.max_depth]}
            self.asks = {level.price: level for level in asks[:self.max_depth]}
            self.last_update_id = update_id
            self.last_update_time = time.time()

    async def apply_update(self, bids: list[OrderBookLevel], asks: list[OrderBookLevel], update_id: int) -> bool:
        """Apply an incremental order book update. Returns True if applied successfully."""
        async with self._lock:
            # Check for gaps
            if self.last_update_id > 0 and update_id != self.last_update_id + 1:
                logger.warning(f"Order book gap detected for {self.symbol}: expected {self.last_update_id + 1}, got {update_id}")
                return False

            # Apply bid updates
            for level in bids:
                if level.quantity == 0:
                    self.bids.pop(level.price, None)
                else:
                    self.bids[level.price] = level

            # Apply ask updates
            for level in asks:
                if level.quantity == 0:
                    self.asks.pop(level.price, None)
                else:
                    self.asks[level.price] = level

            # Trim to max depth
            if len(self.bids) > self.max_depth:
                sorted_bids = sorted(self.bids.items(), key=lambda x: x[0], reverse=True)
                self.bids = dict(sorted_bids[:self.max_depth])

            if len(self.asks) > self.max_depth:
                sorted_asks = sorted(self.asks.items(), key=lambda x: x[0])
                self.asks = dict(sorted_asks[:self.max_depth])

            self.last_update_id = update_id
            self.last_update_time = time.time()
            return True

    def get_snapshot(self, depth: int = 20) -> OrderBookSnapshot:
        """Get current order book snapshot."""
        bids = sorted(self.bids.values(), key=lambda x: x.price, reverse=True)[:depth]
        asks = sorted(self.asks.values(), key=lambda x: x.price)[:depth]
        return OrderBookSnapshot(
            symbol=self.symbol,
            timestamp=_utcnow(),
            bids=bids,
            asks=asks,
            sequence=self.last_update_id,
        )

    def get_best_bid(self) -> Optional[OrderBookLevel]:
        if not self.bids:
            return None
        return max(self.bids.values(), key=lambda x: x.price)

    def get_best_ask(self) -> Optional[OrderBookLevel]:
        if not self.asks:
            return None
        return min(self.asks.values(), key=lambda x: x.price)


class FundingRateTracker:
    """Tracks funding rates for perpetual futures."""

    def __init__(self):
        self.rates: dict[str, list[FundingRateData]] = {}
        self._lock = asyncio.Lock()
        self.max_history = 1000

    async def add_rate(self, rate: FundingRateData) -> None:
        async with self._lock:
            if rate.symbol not in self.rates:
                self.rates[rate.symbol] = []
            self.rates[rate.symbol].append(rate)
            # Trim history
            if len(self.rates[rate.symbol]) > self.max_history:
                self.rates[rate.symbol] = self.rates[rate.symbol][-self.max_history:]

    async def get_latest(self, symbol: str) -> Optional[FundingRateData]:
        async with self._lock:
            rates = self.rates.get(symbol, [])
            return rates[-1] if rates else None

    async def get_history(self, symbol: str, since: Optional[datetime] = None, limit: int = 100) -> list[FundingRateData]:
        async with self._lock:
            rates = self.rates.get(symbol, [])
            if since:
                rates = [r for r in rates if r.timestamp >= since]
            return rates[-limit:]

    async def get_funding_estimate(self, symbol: str) -> Optional[Decimal]:
        """Estimate next funding rate based on recent history."""
        async with self._lock:
            rates = self.rates.get(symbol, [])
            if not rates:
                return None
            # Simple exponential moving average
            alpha = 0.3
            ema = rates[0].funding_rate
            for r in rates[1:]:
                ema = alpha * r.funding_rate + (1 - alpha) * ema
            return ema


class DataQualityValidator:
    """Validates incoming market data for quality issues."""

    def __init__(self, max_price_deviation: float = 0.1, max_volume_zscore: float = 5.0):
        self.max_price_deviation = max_price_deviation
        self.max_volume_zscore = max_volume_zscore
        self.price_history: dict[str, deque] = {}
        self.volume_history: dict[str, deque] = {}
        self.max_history = 1000

    def validate_trade(self, trade: TradeData) -> tuple[bool, list[str]]:
        """Validate a single trade. Returns (is_valid, issues)."""
        issues = []

        if trade.price <= 0:
            issues.append("Price must be positive")
        if trade.quantity <= 0:
            issues.append("Quantity must be positive")
        if trade.timestamp > _utcnow() + timedelta(seconds=10):
            issues.append("Trade timestamp in future")

        # Check for price outliers
        symbol = trade.symbol
        if symbol in self.price_history and len(self.price_history[symbol]) > 10:
            prices = [float(t.price) for t in self.price_history[symbol]]
            mean_price = sum(prices) / len(prices)
            std_price = (sum((p - mean_price) ** 2 for p in prices) / len(prices)) ** 0.5
            if std_price > 0:
                z_score = abs(float(trade.price) - mean_price) / std_price
                if z_score > self.max_price_deviation:
                    issues.append(f"Price z-score {z_score:.2f} exceeds threshold {self.max_price_deviation}")

        return len(issues) == 0, issues

    def validate_ohlcv(self, ohlcv: OHLCV) -> tuple[bool, list[str]]:
        """Validate an OHLCV bar."""
        issues = []

        if ohlcv.high < ohlcv.low:
            issues.append("High < Low")
        if ohlcv.high < ohlcv.open or ohlcv.high < ohlcv.close:
            issues.append("High < Open/Close")
        if ohlcv.low > ohlcv.open or ohlcv.low > ohlcv.close:
            issues.append("Low > Open/Close")
        if ohlcv.open <= 0 or ohlcv.high <= 0 or ohlcv.low <= 0 or ohlcv.close <= 0:
            issues.append("Price must be positive")
        if ohlcv.volume < 0:
            issues.append("Volume cannot be negative")

        # Check for gaps
        if ohlcv.symbol in self.price_history:
            last_bar = self.price_history[ohlcv.symbol][-1] if self.price_history[ohlcv.symbol] else None
            if last_bar and ohlcv.open_time <= last_bar.open_time:
                issues.append("Non-monotonic timestamp")

        return len(issues) == 0, issues

    def add_trade(self, trade: TradeData) -> None:
        if trade.symbol not in self.price_history:
            self.price_history[trade.symbol] = deque(maxlen=self.max_history)
            self.volume_history[trade.symbol] = deque(maxlen=self.max_history)
        self.price_history[trade.symbol].append(trade)
        self.volume_history[trade.symbol].append(trade)

    def add_ohlcv(self, ohlcv: OHLCV) -> None:
        if ohlcv.symbol not in self.price_history:
            self.price_history[ohlcv.symbol] = deque(maxlen=self.max_history)
        self.price_history[ohlcv.symbol].append(ohlcv)


class BinanceDataIngestion(DataIngestion):
    """Binance REST + WebSocket data ingestion with enhanced features."""

    def __init__(self, config: DataSourceConfig):
        self.config = config
        self._session: aiohttp.ClientSession | None = None
        self._ws_client: websockets.WebSocketClientProtocol | None = None
        self._running = False
        self._event_bus = get_event_bus()
        self._semaphore: asyncio.Semaphore | None = None
        self._session_lock = asyncio.Lock()
        self._reconnect_task: asyncio.Task | None = None
        self._ws_reconnect_attempts = 0

        # Enhanced features
        self.order_books: dict[str, OrderBookReconstructor] = {}
        self.funding_tracker = FundingRateTracker()
        self.quality_validator = DataQualityValidator()
        self._trade_buffer: dict[str, list[TradeData]] = {}
        self._ohlcv_buffer: dict[str, deque] = {}

    @property
    def session(self) -> aiohttp.ClientSession | None:
        return self._session

    async def _ensure_session(self):
        """Ensure aiohttp session exists (created once)."""
        import aiohttp
        async with self._session_lock:
            if self._session is None or self._session.closed:
                self._session = aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=30),
                    connector=aiohttp.TCPConnector(limit=100)
                )
            return self._session

    async def start(self):
        self._running = True
        await self._ensure_session()
        self._semaphore = asyncio.Semaphore(self.config.rate_limit // 60)

    async def stop(self):
        self._running = False
        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
        if self._session and not self._session.closed:
            await self._session.close()
        if self._ws_client:
            await self._ws_client.close()

    async def _rate_limited_get(self, url: str, params: dict = None) -> dict:
        async with self._semaphore:
            session = await self._ensure_session()
            async with session.get(url, params=params) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def fetch_historical(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[dict]:
        """Fetch historical klines from Binance REST API with gap detection."""
        if self._session is None or self._session.closed:
            await self.start()

        all_klines = []
        current_start = start
        limit = 1000  # Binance max per request

        while current_start < end:
            params = {
                "symbol": symbol,
                "interval": timeframe,
                "startTime": int(current_start.timestamp() * 1000),
                "endTime": int(end.timestamp() * 1000),
                "limit": limit,
            }

            url = f"{self.config.base_url}/api/v3/klines"
            data = await self._rate_limited_get(url, params)

            if not data:
                break

            for k in data:
                all_klines.append({
                    "symbol": symbol,
                    "interval": timeframe,
                    "open_time": datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc),
                    "close_time": datetime.fromtimestamp(k[6] / 1000, tz=timezone.utc),
                    "open_price": Decimal(str(k[1])),
                    "high_price": Decimal(str(k[2])),
                    "low_price": Decimal(str(k[3])),
                    "close_price": Decimal(str(k[4])),
                    "volume": Decimal(str(k[5])),
                    "trades": k[8],
                    "is_closed": True,
                })

            # Gap detection
            if len(data) < limit:
                logger.warning(f"Potential gap in data for {symbol} {timeframe}: received {len(data)} < {limit}")

            # Move to next batch
            current_start = datetime.fromtimestamp(data[-1][6] / 1000, tz=timezone.utc) + timedelta(milliseconds=1)
            await asyncio.sleep(0.1)

        logger.info(f"Fetched {len(all_klines)} klines for {symbol} {timeframe}")
        return all_klines

    async def fetch_ticker_24h(self, symbol: str) -> dict:
        """Fetch 24h ticker statistics."""
        if self._session is None or self._session.closed:
            await self.start()
        url = f"{self.config.base_url}/api/v3/ticker/24hr"
        return await self._rate_limited_get(url, {"symbol": symbol})

    async def fetch_order_book(self, symbol: str, limit: int = 100) -> dict:
        """Fetch order book snapshot."""
        if self._session is None or self._session.closed:
            await self.start()
        url = f"{self.config.base_url}/api/v3/depth"
        return await self._rate_limited_get(url, {"symbol": symbol, "limit": limit})

    async def fetch_funding_rate(self, symbol: str, limit: int = 100) -> list[dict]:
        """Fetch funding rate history."""
        if self._session is None or self._session.closed:
            await self.start()
        url = f"{self.config.base_url}/fapi/v1/fundingRate"
        return await self._rate_limited_get(url, {"symbol": symbol, "limit": limit})

    async def fetch_mark_price(self, symbol: str) -> dict:
        """Fetch mark price and funding rate."""
        if self._session is None or self._session.closed:
            await self.start()
        url = f"{self.config.base_url}/fapi/v1/premiumIndex"
        return await self._rate_limited_get(url, {"symbol": symbol})

    async def subscribe_realtime(self, symbol: str, timeframe: str = "1m"):
        """Subscribe to real-time kline/trade/book streams with auto-reconnect."""
        if self._ws_reconnect_attempts >= self.config.ws_max_reconnect_attempts:
            logger.error(f"Max reconnection attempts reached for {symbol}")
            return

        try:
            import websockets
        except ImportError as e:
            raise ImportError("websockets package required for real-time subscription") from e

        if not self._running:
            await self.start()

        # Initialize order book reconstructor
        if symbol not in self.order_books:
            self.order_books[symbol] = OrderBookReconstructor(symbol)

        streams = f"{symbol.lower()}@kline_{timeframe}/{symbol.lower()}@trade/{symbol.lower()}@bookTicker/{symbol.lower()}@depth@100ms"
        url = f"{self.config.ws_url}/ws/{streams}"

        while self._running and self._ws_reconnect_attempts < self.config.ws_max_reconnect_attempts:
            try:
                async with websockets.connect(
                    url,
                    ping_interval=self.config.ws_ping_interval,
                    ping_timeout=self.config.ws_ping_timeout,
                    close_timeout=10,
                ) as ws:
                    self._ws_client = ws
                    self._ws_reconnect_attempts = 0
                    logger.info(f"WebSocket connected for {symbol} {streams}")

                    try:
                        async for raw in ws:
                            if not self._running:
                                break
                            try:
                                msg = json.loads(raw)
                            except (TypeError, ValueError):
                                continue
                            event = await self._parse_ws_message(msg, symbol, timeframe)
                            if event is not None:
                                await self._event_bus.publish(event)
                    except websockets.exceptions.ConnectionClosed:
                        logger.warning(f"WebSocket closed for {symbol}, reconnecting...")
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        logger.error(f"WebSocket error for {symbol}: {e}")

                    if self._running:
                        self._ws_reconnect_attempts += 1
                        wait_time = self.config.ws_reconnect_interval * (2 ** min(self._ws_reconnect_attempts, 5))
                        logger.info(f"Reconnecting in {wait_time}s (attempt {self._ws_reconnect_attempts})")
                        await asyncio.sleep(wait_time)

            except Exception as e:
                logger.error(f"WebSocket connection failed for {symbol}: {e}")
                self._ws_reconnect_attempts += 1
                await asyncio.sleep(self.config.ws_reconnect_interval)

    async def _parse_ws_message(self, msg: dict, symbol: str, timeframe: str) -> Event | None:
        event_type = msg.get("e")
        if event_type == "kline":
            k = msg.get("k", {})
            ohlcv = OHLCV(
                symbol=msg.get("s", symbol),
                timeframe=k.get("i", timeframe),
                open_time=datetime.fromtimestamp(k.get("t", 0) / 1000, tz=timezone.utc),
                close_time=datetime.fromtimestamp(k.get("T", 0) / 1000, tz=timezone.utc),
                open_price=Decimal(str(k.get("o", "0"))),
                high_price=Decimal(str(k.get("h", "0"))),
                low_price=Decimal(str(k.get("l", "0"))),
                close_price=Decimal(str(k.get("c", "0"))),
                volume=Decimal(str(k.get("v", "0"))),
                trades=int(k.get("n", 0)),
                is_closed=bool(k.get("x", False)),
            )

            # Validate and buffer
            valid, issues = self.quality_validator.validate_ohlcv(ohlcv)
            if not valid:
                logger.warning(f"Invalid OHLCV for {symbol}: {issues}")
            else:
                self.quality_validator.add_ohlcv(ohlcv)

            return KlineEvent(
                symbol=msg.get("s", symbol),
                interval=k.get("i", timeframe),
                open_time=ohlcv.open_time,
                close_time=ohlcv.close_time,
                open_price=ohlcv.open,
                high_price=ohlcv.high,
                low_price=ohlcv.low,
                close_price=ohlcv.close,
                volume=ohlcv.volume,
                trades=ohlcv.trades,
                is_closed=ohlcv.is_closed,
            )

        if event_type == "trade":
            trade = TradeData(
                symbol=msg.get("s", symbol),
                trade_id=str(msg.get("t", "")),
                price=Decimal(str(msg.get("p", "0"))),
                quantity=Decimal(str(msg.get("q", "0"))),
                side=OrderSide.BUY if msg.get("m") is False else OrderSide.SELL,
                is_maker=bool(msg.get("m", False)),
                timestamp=datetime.fromtimestamp(msg.get("T", 0) / 1000, tz=timezone.utc),
            )

            # Validate and track
            valid, issues = self.quality_validator.validate_trade(trade)
            if not valid:
                logger.warning(f"Invalid trade for {symbol}: {issues}")
            else:
                self.quality_validator.add_trade(trade)

            return TradeEvent(
                symbol=msg.get("s", symbol),
                trade_id=str(msg.get("t", "")),
                price=trade.price,
                quantity=trade.quantity,
                side=trade.side,
                is_maker=trade.is_maker,
                timestamp=trade.timestamp,
            )

        if event_type == "depthUpdate" or event_type == "depth":
            # Order book update
            u = msg.get("u", 0)
            b = msg.get("b", [])
            a = msg.get("a", [])

            bids = [OrderBookLevel(price=Decimal(b[0]), quantity=Decimal(b[1])) for b in b]
            asks = [OrderBookLevel(price=Decimal(a[0]), quantity=Decimal(a[1])) for a in a]

            if symbol in self.order_books:
                success = await self.order_books[symbol].apply_update(bids, asks, u)
                if success:
                    snapshot = self.order_books[symbol].get_snapshot()
                    return TickerEvent(
                        symbol=symbol,
                        bid=snapshot.best_bid.price if snapshot.best_bid else Decimal("0"),
                        ask=snapshot.best_ask.price if snapshot.best_ask else Decimal("0"),
                        bid_qty=snapshot.best_bid.quantity if snapshot.best_bid else Decimal("0"),
                        ask_qty=snapshot.best_ask.quantity if snapshot.best_ask else Decimal("0"),
                    )

        if event_type == "bookTicker" or ("b" in msg and "a" in msg and "e" not in msg):
            return TickerEvent(
                symbol=msg.get("s", symbol),
                bid=Decimal(str(msg.get("b", "0"))),
                ask=Decimal(str(msg.get("a", "0"))),
                bid_qty=Decimal(str(msg.get("B", "0"))),
                ask_qty=Decimal(str(msg.get("A", "0"))),
            )

        if event_type == "markPriceUpdate" or event_type == "markPrice":
            # Funding rate update
            funding = FundingRateData(
                symbol=msg.get("s", symbol),
                timestamp=datetime.fromtimestamp(msg.get("T", 0) / 1000, tz=timezone.utc),
                funding_rate=Decimal(str(msg.get("r", "0"))),
                mark_price=Decimal(str(msg.get("p", "0"))),
                index_price=Decimal(str(msg.get("i", "0"))),
                next_funding_time=datetime.fromtimestamp(msg.get("T", 0) / 1000 + 8 * 3600, tz=timezone.utc),
            )
            await self.funding_tracker.add_rate(funding)

            return TickerEvent(
                symbol=msg.get("s", symbol),
                bid=Decimal(str(msg.get("b", "0"))),
                ask=Decimal(str(msg.get("a", "0"))),
                bid_qty=Decimal(str(msg.get("B", "0"))),
                ask_qty=Decimal(str(msg.get("A", "0"))),
            )

        return None

    async def fetch_funding_rate(self, symbol: str, limit: int = 100) -> list[dict]:
        """Fetch funding rate history."""
        if self._session is None or self._session.closed:
            await self.start()
        url = f"{self.config.base_url}/fapi/v1/fundingRate"
        return await self._rate_limited_get(url, {"symbol": symbol, "limit": limit})

    async def fetch_funding_history(self, symbol: str, start: datetime, end: datetime) -> list[FundingRateData]:
        """Fetch funding rate history from tracker."""
        return await self.funding_tracker.get_history(symbol, since=start, limit=1000)

    async def get_order_book_snapshot(self, symbol: str, depth: int = 20) -> OrderBookSnapshot | None:
        """Get current order book snapshot."""
        if symbol in self.order_books:
            return self.order_books[symbol].get_snapshot(depth)
        return None

    def get_funding_estimate(self, symbol: str) -> Optional[Decimal]:
        """Get estimated next funding rate."""
        return self.funding_tracker.get_funding_estimate(symbol)


class DataIngestionManager:
    """Manages multiple data sources and coordinates ingestion."""

    def __init__(self):
        self.sources: dict[str, DataIngestion] = {}
        self._event_bus = get_event_bus()

    def register_source(self, source: DataIngestion):
        self.sources[source.config.name] = source

    async def start_all(self):
        for source in self.sources.values():
            if source.config.enabled:
                await source.start()

    async def stop_all(self):
        for source in self.sources.values():
            await source.stop()

    async def fetch_all_historical(
        self,
        symbols: list[str],
        timeframes: list[str],
        start: datetime,
        end: datetime,
        venue: str = "binance",
    ) -> dict[str, dict[str, list[dict]]]:
        """Fetch historical data for all symbols/timeframes from a venue."""
        source = self.sources.get(venue)
        if not source:
            raise ValueError(f"Venue {venue} not registered")

        results = {}
        for symbol in symbols:
            results[symbol] = {}
            for tf in timeframes:
                results[symbol][tf] = await source.fetch_historical(symbol, tf, start, end)

        return results


# Global ingestion manager
_ingestion_manager: DataIngestionManager | None = None


def get_ingestion_manager() -> DataIngestionManager:
    global _ingestion_manager
    if _ingestion_manager is None:
        _ingestion_manager = DataIngestionManager()
    return _ingestion_manager


__all__ = [
    "OHLCV",
    "Tick",
    "TradeData",
    "FundingRateData",
    "OrderBookSnapshot",
    "OrderBookLevel",
    "OrderBookReconstructor",
    "FundingRateTracker",
    "DataQualityValidator",
    "DataSourceConfig",
    "DataIngestion",
    "BinanceDataIngestion",
    "DataIngestionManager",
    "get_ingestion_manager",
]