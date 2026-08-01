from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import aiohttp

from cryptobot.core.bus import get_event_bus
from cryptobot.core.events import (
    Event,
    KlineEvent,
    OrderSide,
    TickerEvent,
    TradeEvent,
)


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


class BinanceDataIngestion(DataIngestion):
    """Binance REST + WebSocket data ingestion."""

    def __init__(self, config: DataSourceConfig):
        self.config = config
        self._session: "aiohttp.ClientSession | None" = None
        self._ws_client = None
        self._running = False
        self._event_bus = get_event_bus()
        self._semaphore: asyncio.Semaphore | None = None
        self._session_lock = asyncio.Lock()

    @property
    def session(self) -> "aiohttp.ClientSession | None":
        return self._session

    async def _ensure_session(self):
        """Ensure aiohttp session exists (created once)."""
        import aiohttp
        async with self._session_lock:
            if self._session is None or self._session.closed:
                self._session = aiohttp.ClientSession()
            return self._session

    async def start(self):
        self._running = True
        await self._ensure_session()
        self._semaphore = asyncio.Semaphore(self.config.rate_limit // 60)

    async def stop(self):
        self._running = False
        if self._session and not self._session.closed:
            await self._session.close()
        if self._ws_client:
            await self._ws_client.stop()

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
        """Fetch historical klines from Binance REST API."""
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
                    "open_time": datetime.fromtimestamp(k[0] / 1000),
                    "close_time": datetime.fromtimestamp(k[6] / 1000),
                    "open_price": Decimal(str(k[1])),
                    "high_price": Decimal(str(k[2])),
                    "low_price": Decimal(str(k[3])),
                    "close_price": Decimal(str(k[4])),
                    "volume": Decimal(str(k[5])),
                    "trades": k[8],
                    "is_closed": True,
                })

            # Move to next batch
            current_start = datetime.fromtimestamp(data[-1][6] / 1000) + timedelta(milliseconds=1)

            # Small delay to respect rate limits
            await asyncio.sleep(0.1)

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
        """Subscribe to real-time kline/trade streams for a symbol."""
        try:
            import websockets
        except ImportError as e:
            raise ImportError("websockets package required for real-time subscription") from e

        if not self._running:
            await self.start()

        streams = f"{symbol.lower()}@kline_{timeframe}/{symbol.lower()}@trade/{symbol.lower()}@bookTicker"
        url = f"{self.config.ws_url}/ws/{streams}"

        async with websockets.connect(url) as ws:
            self.ws_client = ws
            try:
                async for raw in ws:
                    if not self._running:
                        break
                    try:
                        msg = json.loads(raw)
                    except (TypeError, ValueError):
                        continue
                    event = self._parse_ws_message(msg, symbol, timeframe)
                    if event is not None:
                        await self._event_bus.publish(event)
            except asyncio.CancelledError:
                pass

    def _parse_ws_message(self, msg: dict, symbol: str, timeframe: str) -> Event | None:
        event_type = msg.get("e")
        if event_type == "kline":
            k = msg.get("k", {})
            return KlineEvent(
                symbol=msg.get("s", symbol),
                interval=k.get("i", timeframe),
                open_time=datetime.fromtimestamp(k.get("t", 0) / 1000),
                close_time=datetime.fromtimestamp(k.get("T", 0) / 1000),
                open_price=Decimal(str(k.get("o", "0"))),
                high_price=Decimal(str(k.get("h", "0"))),
                low_price=Decimal(str(k.get("l", "0"))),
                close_price=Decimal(str(k.get("c", "0"))),
                volume=Decimal(str(k.get("v", "0"))),
                trades=int(k.get("n", 0)),
                is_closed=bool(k.get("x", False)),
            )
        if event_type == "trade":
            return TradeEvent(
                symbol=msg.get("s", symbol),
                trade_id=str(msg.get("t", "")),
                price=Decimal(str(msg.get("p", "0"))),
                quantity=Decimal(str(msg.get("q", "0"))),
                side=OrderSide.BUY if msg.get("m") is False else OrderSide.SELL,
                is_maker=bool(msg.get("m", False)),
                timestamp=datetime.fromtimestamp(msg.get("T", 0) / 1000),
            )
        if event_type == "bookTicker" or ("b" in msg and "a" in msg and "e" not in msg):
            return TickerEvent(
                symbol=msg.get("s", symbol),
                bid=Decimal(str(msg.get("b", "0"))),
                ask=Decimal(str(msg.get("a", "0"))),
                bid_qty=Decimal(str(msg.get("B", "0"))),
                ask_qty=Decimal(str(msg.get("A", "0"))),
            )
        return None


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
