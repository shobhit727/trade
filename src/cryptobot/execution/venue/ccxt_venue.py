"""Generic ccxt venue adapter — one class, any exchange (Seed Phase step 2).

``CcxtVenue`` parameterizes the former Binance-only adapter by ``exchange_id``
so every ccxt-supported venue (binance, bybit, okx, kraken, ...) plugs into
the execution engine through the same ``Venue`` interface. Exchange-specific
quirks live in small override tables instead of subclasses where possible.

Off-line / not-configured behaviour is unchanged: orders are rejected with a
clear status and no network call is attempted.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from cryptobot.config import settings
from cryptobot.core.events import OrderEvent, OrderSide, OrderStatus, OrderType

try:
    import ccxt.async_support as ccxt_async
except ImportError as _e:
    ccxt_async = None
    _IMPORT_ERROR = _e
else:
    _IMPORT_ERROR = None

from cryptobot.execution.venue.base import Venue

logger = logging.getLogger(__name__)

# Quote-asset suffixes used to normalize EXCHANGESYMBOL -> BASE/QUOTE.
_KNOWN_QUOTES = ("USDT", "USDC", "FDUSD", "TUSD", "BUSD", "USD", "BTC", "ETH")

# Order-type name overrides per exchange; exchanges not listed use DEFAULT.
_ORDER_TYPE_MAPS: dict[str, dict[OrderType, str]] = {
    "binance": {
        OrderType.MARKET: "market",
        OrderType.LIMIT: "limit",
        OrderType.STOP_LOSS: "stop_market",
        OrderType.STOP_LOSS_LIMIT: "stop",
        OrderType.TAKE_PROFIT: "take_profit_market",
        OrderType.TAKE_PROFIT_LIMIT: "take_profit",
        OrderType.LIMIT_MAKER: "limit_maker",
    },
    "bybit": {
        OrderType.MARKET: "market",
        OrderType.LIMIT: "limit",
        OrderType.STOP_LOSS: "market",
        OrderType.STOP_LOSS_LIMIT: "limit",
        OrderType.TAKE_PROFIT: "market",
        OrderType.TAKE_PROFIT_LIMIT: "limit",
        OrderType.LIMIT_MAKER: "limit",
    },
}
_ORDER_TYPE_DEFAULT = {
    OrderType.MARKET: "market",
    OrderType.LIMIT: "limit",
    OrderType.STOP_LOSS: "stop_market",
    OrderType.STOP_LOSS_LIMIT: "stop",
    OrderType.TAKE_PROFIT: "take_profit_market",
    OrderType.TAKE_PROFIT_LIMIT: "take_profit",
    OrderType.LIMIT_MAKER: "limit_maker",
}


class CcxtVenue(Venue):
    """Live/testnet adapter for any ccxt exchange using ccxt async."""

    def __init__(
        self,
        exchange_id: str = "binance",
        api_key: str | None = None,
        api_secret: str | None = None,
        market_type: str = "future",
        sandbox: bool | None = None,
        rate_limit_ms: int = 200,
        max_retries: int = 3,
    ):
        self.exchange_id = exchange_id.lower()
        self.api_key = api_key if api_key is not None else settings.exchange.api_key
        self.api_secret = api_secret if api_secret is not None else settings.exchange.api_secret
        self.market_type = market_type
        if sandbox is None:
            sandbox = settings.exchange.testnet
        self.sandbox = sandbox
        self.rate_limit_ms = rate_limit_ms
        self.max_retries = max_retries
        self._exchange: Any | None = None
        self._closed = False

    # ------------------------------------------------------------ lifecycle

    def _ensure_exchange(self) -> Any:
        if ccxt_async is None:
            raise RuntimeError(f"ccxt is not installed: {_IMPORT_ERROR}")
        if self._exchange is not None:
            return self._exchange
        cls = getattr(ccxt_async, self.exchange_id, None)
        if cls is None:
            raise ValueError(f"unknown ccxt exchange id: {self.exchange_id}")
        options: dict[str, Any] = {
            "defaultType": self.market_type,
            "adjustForTimeDifference": True,
            "rateLimit": self.rate_limit_ms,
            "enableRateLimit": True,
        }
        if self.sandbox:
            options["sandboxMode"] = True
        self._exchange = cls(
            {
                "apiKey": self.api_key,
                "secret": self.api_secret,
                "enableRateLimit": True,
                "options": options,
            }
        )
        return self._exchange

    async def close(self) -> None:
        if self._exchange is not None and not self._closed:
            try:
                await self._exchange.close()
            except Exception as exc:
                logger.warning("%s close failed: %s", self.exchange_id, exc)
            self._closed = True

    @staticmethod
    def _has_credentials(api_key: str, api_secret: str) -> bool:
        return bool(api_key and api_secret)

    def _reject(self, order: OrderEvent, status: OrderStatus, message: str) -> OrderEvent:
        order.status = status
        order.__post_init__()
        if "error" not in order.payload:
            order.payload["error"] = message
        return order

    # --------------------------------------------------------------- mapping

    def _map_order_type(self, type_: OrderType) -> str:
        table = _ORDER_TYPE_MAPS.get(self.exchange_id, _ORDER_TYPE_DEFAULT)
        return table.get(type_, "limit")

    def _map_side(self, side: OrderSide) -> str:
        return "buy" if side == OrderSide.BUY else "sell"

    def _map_symbol(self, symbol: str) -> str:
        """Normalize to ccxt unified form (BASE/QUOTE); passthrough if already."""
        if "/" in symbol:
            return symbol
        for quote in _KNOWN_QUOTES:
            if symbol.endswith(quote) and len(symbol) > len(quote):
                return f"{symbol[: -len(quote)]}/{quote}"
        return symbol

    # ---------------------------------------------------------- order submit

    async def submit_order(self, order: OrderEvent) -> OrderEvent:
        if not self._has_credentials(self.api_key, self.api_secret):
            return self._reject(
                order,
                OrderStatus.REJECTED,
                f"{self.exchange_id} credentials missing; set API key/secret env vars",
            )
        if ccxt_async is None:
            return self._reject(order, OrderStatus.REJECTED, f"ccxt not installed: {_IMPORT_ERROR}")

        try:
            exchange = self._ensure_exchange()
        except Exception as exc:
            return self._reject(order, OrderStatus.REJECTED, str(exc))

        symbol = self._map_symbol(order.symbol)
        side = self._map_side(order.side)
        type_ = self._map_order_type(order.type)
        amount = float(order.quantity)

        params: dict[str, Any] = {"type": self.market_type}
        if order.client_order_id:
            params["newClientOrderId"] = order.client_order_id
        if order.reduce_only:
            params["reduceOnly"] = True

        params_typed: Mapping[str, Any] = params

        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            start = time.perf_counter()
            try:
                price: float | None = None
                if type_ == "limit":
                    if order.price is None:
                        return self._reject(order, OrderStatus.REJECTED, "Limit order missing price")
                    price = float(order.price)
                raw = await exchange.create_order(symbol, type_, side, amount, price, params_typed)
                self._record_round_trip(type_, start)
                return self._apply_fill(order, raw)
            except Exception as exc:
                last_exc = exc
                backoff = 0.5 * (2 ** attempt)
                logger.warning(
                    "%s submit_order failed (attempt %d/%d): %s. Retrying in %.1fs",
                    self.exchange_id, attempt + 1, self.max_retries, exc, backoff,
                )
                await asyncio.sleep(backoff)

        return self._reject(order, OrderStatus.REJECTED, str(last_exc) if last_exc else "submit failed")

    @staticmethod
    def _record_round_trip(order_type: str, start: float, venue: str = "ccxt") -> None:
        latency_ms = (time.perf_counter() - start) * 1000.0
        try:
            from cryptobot.monitoring.metrics import record_execution_latency
            record_execution_latency(venue=venue, symbol="-", order_type=order_type, latency=latency_ms / 1000.0)
        except Exception as exc:
            logger.debug("metrics record skipped: %s", exc)

    def _apply_fill(self, order: OrderEvent, raw: Mapping[str, Any]) -> OrderEvent:
        try:
            filled = Decimal(str(raw.get("filled", raw.get("amount", order.quantity))))
            avg_price = raw.get("average") or raw.get("price")
            order.filled_quantity = filled
            if avg_price is not None:
                order.avg_fill_price = Decimal(str(avg_price))
            fee = raw.get("fee") or {}
            if isinstance(fee, Mapping):
                cost = fee.get("cost")
                if cost is not None:
                    order.commission = Decimal(str(cost))
                order.commission_asset = str(fee.get("currency", order.commission_asset))
            order_id = raw.get("id") or order.order_id
            if order_id:
                order.order_id = str(order_id)
            status = raw.get("status")
            if status == "closed":
                order.status = OrderStatus.FILLED
            elif status == "canceled":
                order.status = OrderStatus.CANCELED
            elif status == "open" or status == "new":
                order.status = OrderStatus.PARTIALLY_FILLED if filled > 0 else OrderStatus.NEW
            elif status == "rejected":
                order.status = OrderStatus.REJECTED
            elif status == "expired":
                order.status = OrderStatus.EXPIRED
            else:
                order.status = OrderStatus.FILLED if filled > 0 else OrderStatus.NEW
        except Exception as exc:
            logger.warning("%s apply_fill parsing error: %s; raw=%s", self.exchange_id, exc, raw)
            order.status = OrderStatus.FILLED if order.filled_quantity > 0 else OrderStatus.NEW

        order.__post_init__()
        return order

    # ----------------------------------------------------------- cancels/quotes

    async def cancel_order(self, order_id: str) -> bool:
        if ccxt_async is None or not self._has_credentials(self.api_key, self.api_secret):
            return False
        exchange = self._ensure_exchange()
        try:
            await exchange.cancel_order(order_id)
            return True
        except Exception as exc:
            logger.warning("%s cancel_order failed for %s: %s", self.exchange_id, order_id, exc)
            return False

    async def place_protective_stop(
        self,
        symbol: str,
        side: str,
        quantity: float,
        stop_price: float,
    ) -> str | None:
        """Exchange-native stop-market reduce-only order (host-death protection).

        ``side`` is the closing side ("sell" for a long). Returns the exchange
        order id, or None when unsupported/unavailable. The exchange honours
        this even if our host is dead - that is the entire point.
        """
        if ccxt_async is None or not self._has_credentials(self.api_key, self.api_secret):
            return None
        try:
            exchange = self._ensure_exchange()
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s protective stop unavailable: %s", self.exchange_id, exc)
            return None
        mapped = self._map_symbol(symbol)
        type_ = "market"
        if self.exchange_id == "binance":
            type_ = "stop_market"
        params: dict[str, Any] = {
            "type": self.market_type,
            "reduceOnly": True,
            "stopPrice": stop_price,
        }
        try:
            raw = await exchange.create_order(mapped, type_, side, quantity, None, params)
            order_id = raw.get("id")
            logger.info("protective stop placed on %s (%s %s @ %s): %s",
                        symbol, side, quantity, stop_price, order_id)
            return str(order_id) if order_id else None
        except Exception as exc:  # noqa: BLE001
            logger.warning("protective stop failed on %s: %s", symbol, exc)
            return None

    async def get_price(self, symbol: str) -> Decimal:
        if ccxt_async is None or not self._has_credentials(self.api_key, self.api_secret):
            return Decimal("0")
        exchange = self._ensure_exchange()
        start = time.perf_counter()
        try:
            mapped = self._map_symbol(symbol)
            ticker = await exchange.fetch_ticker(mapped)
            self._record_round_trip("quote", start, venue=self.exchange_id)
            last = ticker.get("last") or ticker.get("close")
            return Decimal(str(last)) if last is not None else Decimal("0")
        except Exception as exc:
            logger.warning("%s get_price failed: %s", self.exchange_id, exc)
            return Decimal("0")


__all__ = ["CcxtVenue"]
