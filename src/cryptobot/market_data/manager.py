from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import aiohttp

import redis.asyncio as redis

from cryptobot.config import settings
from cryptobot.core.events import (
    Event,
    EventType,
    FundingRateEvent,
    KlineEvent,
    OrderBookEvent,
    TickerEvent,
    TradeEvent,
)

logger = logging.getLogger(__name__)


class BinanceWSClient:
    def __init__(self, symbols: list[str] | None = None, timeframes: list[str] | None = None,
                 ws_url: str | None = None):
        self.ws_url = ws_url if ws_url is not None else settings.exchange.ws_url
        self.session: aiohttp.ClientSession | None = None
        self.ws: aiohttp.ClientWebSocketResponse | None = None
        self.running = False
        self.subscriptions: set[str] = set()
        self.callbacks: dict[str, list[Callable]] = defaultdict(list)
        self._reconnect_delay = 1
        self._max_reconnect_delay = 60
        self._last_ping = 0
        self._ping_interval = 20
        self._symbols = symbols or settings.exchange.symbols or [settings.exchange.default_symbol]
        if not symbols and not settings.exchange.symbols:
            logger.warning("BinanceWSClient: no symbols configured; falling back to default_symbol=%s", settings.exchange.default_symbol)
        self._timeframes = timeframes or settings.exchange.timeframes or ["1m"]
        if not timeframes and not settings.exchange.timeframes:
            logger.warning("BinanceWSClient: no timeframes configured; falling back to ['1m']")

    async def start(self):
        import aiohttp
        self.running = True
        self.session = aiohttp.ClientSession()
        await self._connect()
        asyncio.create_task(self._heartbeat())
        asyncio.create_task(self._listen())

    async def stop(self):
        self.running = False
        if self.ws:
            await self.ws.close()
        if self.session:
            await self.session.close()

    async def _connect(self):
        try:
            streams = self._build_streams()
            url = f"{self.ws_url}/stream?streams={'/'.join(streams)}"
            self.ws = await self.session.ws_connect(url, heartbeat=30)
            self._reconnect_delay = 1
            logger.info("Connected to Binance WS: %s", url)
        except Exception as e:
            logger.warning("WS connection failed: %s", e)
            await self._reconnect()

    def _build_streams(self) -> list[str]:
        streams = []
        for symbol in self._symbols:
            s = symbol.lower()
            streams.append(f"{s}@ticker")
            streams.append(f"{s}@depth{settings.market_data.orderbook_depth}@100ms")
            streams.append(f"{s}@trade")
            for tf in self._timeframes:
                streams.append(f"{s}@kline_{tf}")
            streams.append(f"{s}@markPrice@1s")
        return streams

    async def _reconnect(self):
        if not self.running:
            return
        delay = min(self._reconnect_delay, self._max_reconnect_delay)
        logger.info("Reconnecting in %.1fs", delay)
        await asyncio.sleep(delay)
        self._reconnect_delay *= 2
        await self._connect()

    async def _heartbeat(self):
        while self.running:
            await asyncio.sleep(self._ping_interval)
            if self.ws and not self.ws.closed:
                try:
                    await self.ws.ping()
                    self._last_ping = time.time()
                except Exception:
                    await self._reconnect()

    async def _listen(self):
        import aiohttp
        while self.running:
            try:
                if not self.ws or self.ws.closed:
                    await self._reconnect()
                    continue
                msg = await self.ws.receive()
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._handle_message(msg.data)
                elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
                    await self._reconnect()
            except Exception as e:
                logger.warning("WS listen error: %s", e)
                await asyncio.sleep(1)

    async def _handle_message(self, data: str):
        try:
            msg = json.loads(data)
            stream = msg.get("stream", "")
            payload = msg.get("data", {})
            if not stream or not payload:
                return

            if "@ticker" in stream:
                await self._handle_ticker(payload)
            elif "@depth" in stream:
                await self._handle_orderbook(payload)
            elif "@trade" in stream:
                await self._handle_trade(payload)
            elif "@kline_" in stream:
                await self._handle_kline(payload)
            elif "@markPrice" in stream:
                await self._handle_mark_price(payload)
        except Exception as e:
            logger.warning("Message handling error: %s", e)

    async def _handle_ticker(self, data: dict):
        symbol = data.get("s", "")
        event = TickerEvent(
            symbol=symbol,
            price=Decimal(data.get("c", "0")),
            bid=Decimal(data.get("b", "0")),
            ask=Decimal(data.get("a", "0")),
            bid_qty=Decimal(data.get("B", "0")),
            ask_qty=Decimal(data.get("A", "0")),
            high_24h=Decimal(data.get("h", "0")),
            low_24h=Decimal(data.get("l", "0")),
            volume_24h=Decimal(data.get("v", "0")),
            change_24h=float(data.get("P", "0")),
            source="binance_ws",
        )
        await self._emit(EventType.TICKER, event)

    async def _handle_orderbook(self, data: dict):
        symbol = data.get("s", "")
        bids = [(Decimal(p), Decimal(q)) for p, q in data.get("b", [])]
        asks = [(Decimal(p), Decimal(q)) for p, q in data.get("a", [])]
        event = OrderBookEvent(
            symbol=symbol,
            bids=bids,
            asks=asks,
            sequence=data.get("u", 0),
            source="binance_ws",
        )
        await self._emit(EventType.ORDERBOOK, event)

    async def _handle_trade(self, data: dict):
        symbol = data.get("s", "")
        from cryptobot.core.events import OrderSide
        event = TradeEvent(
            symbol=symbol,
            trade_id=str(data.get("t", "")),
            price=Decimal(data.get("p", "0")),
            quantity=Decimal(data.get("q", "0")),
            side=OrderSide.SELL if data.get("m", False) else OrderSide.BUY,
            is_maker=data.get("m", False),
            source="binance_ws",
        )
        await self._emit(EventType.TRADE, event)

    async def _handle_kline(self, data: dict):
        k = data.get("k", {})
        symbol = k.get("s", "")
        event = KlineEvent(
            symbol=symbol,
            interval=k.get("i", ""),
            open_time=datetime.fromtimestamp(k.get("t", 0) / 1000),
            close_time=datetime.fromtimestamp(k.get("T", 0) / 1000),
            open_price=Decimal(k.get("o", "0")),
            high_price=Decimal(k.get("h", "0")),
            low_price=Decimal(k.get("l", "0")),
            close_price=Decimal(k.get("c", "0")),
            volume=Decimal(k.get("v", "0")),
            trades=k.get("n", 0),
            is_closed=k.get("x", False),
            source="binance_ws",
        )
        await self._emit(EventType.KLINE, event)

    async def _handle_mark_price(self, data: dict):
        symbol = data.get("s", "")
        event = FundingRateEvent(
            symbol=symbol,
            funding_rate=float(data.get("r", "0")),
            mark_price=Decimal(data.get("p", "0")),
            index_price=Decimal(data.get("i", "0")),
            next_funding_time=datetime.fromtimestamp(data.get("T", 0) / 1000),
            source="binance_ws",
        )
        await self._emit(EventType.FUNDING_RATE, event)

    def subscribe(self, event_type: EventType, callback: Callable):
        self.callbacks[event_type.value].append(callback)

    async def _emit(self, event_type: EventType, event: Event):
        for callback in self.callbacks.get(event_type.value, []):
            try:
                if inspect.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception as e:
                logger.warning("Callback error for %s: %s", event_type, e)


class MarketDataCache:
    def __init__(self):
        self.redis: redis.Redis | None = None
        self.local_cache: dict[str, Any] = {}
        self.ttl = settings.market_data.cache_ttl_seconds

    async def start(self):
        self.redis = redis.Redis(
            host=settings.market_data.redis_host,
            port=settings.market_data.redis_port,
            db=settings.market_data.redis_db,
            max_connections=settings.market_data.redis_max_connections,
            decode_responses=True,
        )

    async def stop(self):
        if self.redis:
            await self.redis.close()

    async def set_ticker(self, event: TickerEvent):
        key = f"ticker:{event.symbol}"
        data = event.to_dict()
        self.local_cache[key] = data
        if self.redis:
            await self.redis.setex(key, self.ttl, json.dumps(data))

    async def get_ticker(self, symbol: str) -> dict | None:
        key = f"ticker:{symbol}"
        if key in self.local_cache:
            return self.local_cache[key]
        if self.redis:
            data = await self.redis.get(key)
            if data:
                return json.loads(data)
        return None

    async def set_orderbook(self, event: OrderBookEvent):
        key = f"orderbook:{event.symbol}"
        data = event.to_dict()
        self.local_cache[key] = data
        if self.redis:
            await self.redis.setex(key, self.ttl, json.dumps(data))

    async def get_orderbook(self, symbol: str) -> dict | None:
        key = f"orderbook:{symbol}"
        if key in self.local_cache:
            return self.local_cache[key]
        if self.redis:
            data = await self.redis.get(key)
            if data:
                return json.loads(data)
        return None

    async def set_kline(self, event: KlineEvent):
        key = f"kline:{event.symbol}:{event.interval}"
        data = event.to_dict()
        self.local_cache[key] = data
        if self.redis:
            await self.redis.setex(key, self.ttl, json.dumps(data))

    async def get_klines(self, symbol: str, interval: str, limit: int = 100) -> list[dict]:
        # In production, use Redis streams or TimescaleDB
        # For now, return from local cache
        key = f"kline:{symbol}:{interval}"
        if key in self.local_cache:
            return [self.local_cache[key]]
        return []

    async def set_funding_rate(self, event: FundingRateEvent):
        key = f"funding:{event.symbol}"
        data = event.to_dict()
        self.local_cache[key] = data
        if self.redis:
            await self.redis.setex(key, self.ttl, json.dumps(data))

    async def get_funding_rate(self, symbol: str) -> dict | None:
        key = f"funding:{symbol}"
        if key in self.local_cache:
            return self.local_cache[key]
        if self.redis:
            data = await self.redis.get(key)
            if data:
                return json.loads(data)
        return None


class MarketDataManager:
    def __init__(self):
        self.ws_client = BinanceWSClient()
        self.cache = MarketDataCache()
        self._callbacks: dict[EventType, list[Callable]] = defaultdict(list)

    async def start(self):
        await self.cache.start()
        self.ws_client.subscribe(EventType.TICKER, self._on_ticker)
        self.ws_client.subscribe(EventType.ORDERBOOK, self._on_orderbook)
        self.ws_client.subscribe(EventType.TRADE, self._on_trade)
        self.ws_client.subscribe(EventType.KLINE, self._on_kline)
        self.ws_client.subscribe(EventType.FUNDING_RATE, self._on_funding)
        await self.ws_client.start()

    async def stop(self):
        await self.ws_client.stop()
        await self.cache.stop()

    def subscribe(self, event_type: EventType, callback: Callable):
        self._callbacks[event_type].append(callback)

    async def _on_ticker(self, event: TickerEvent):
        await self.cache.set_ticker(event)
        await self._emit(EventType.TICKER, event)

    async def _on_orderbook(self, event: OrderBookEvent):
        await self.cache.set_orderbook(event)
        await self._emit(EventType.ORDERBOOK, event)

    async def _on_trade(self, event: TradeEvent):
        await self._emit(EventType.TRADE, event)

    async def _on_kline(self, event: KlineEvent):
        await self.cache.set_kline(event)
        await self._emit(EventType.KLINE, event)

    async def _on_funding(self, event: FundingRateEvent):
        await self.cache.set_funding_rate(event)
        await self._emit(EventType.FUNDING_RATE, event)

    async def _emit(self, event_type: EventType, event: Event):
        for callback in self._callbacks.get(event_type, []):
            try:
                if inspect.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception as e:
                logger.warning("Callback error: %s", e)

    def get_ticker(self, symbol: str) -> TickerEvent | None:
        data = self.cache.local_cache.get(f"ticker:{symbol}")
        if data:
            payload = data.get("payload", data)
            payload = self._coerce_decimal_fields(
                payload,
                {"price", "bid", "ask", "bid_qty", "ask_qty", "high_24h", "low_24h", "volume_24h"},
            )
            return TickerEvent(**payload)
        return None

    def get_orderbook(self, symbol: str) -> OrderBookEvent | None:
        data = self.cache.local_cache.get(f"orderbook:{symbol}")
        if data:
            payload = data.get("payload", data)
            bids = [(Decimal(p), Decimal(q)) for p, q in payload.get("bids", [])]
            asks = [(Decimal(p), Decimal(q)) for p, q in payload.get("asks", [])]
            return OrderBookEvent(
                symbol=payload.get("symbol", ""),
                bids=bids,
                asks=asks,
                sequence=payload.get("sequence", 0),
            )
        return None

    @staticmethod
    def _coerce_decimal_fields(payload: dict, fields: set[str]) -> dict:
        out = dict(payload)
        for field in fields:
            if field in out and not isinstance(out[field], Decimal):
                out[field] = Decimal(str(out[field]))
        return out

    def get_mid_price(self, symbol: str) -> Decimal:
        ob = self.get_orderbook(symbol)
        if ob:
            return ob.mid_price
        ticker = self.get_ticker(symbol)
        if ticker:
            return ticker.price
        return Decimal("0")
