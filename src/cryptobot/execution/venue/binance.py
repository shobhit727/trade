from __future__ import annotations

import asyncio
import logging
import time
from decimal import Decimal
from typing import Any, Dict, Mapping, Optional

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


class BinanceVenue(Venue):
    """Live / testnet Binance adapter using ccxt async.

    Maps an internal ``OrderEvent`` to ccxt's Binance futures / spot
    ``create_order`` call, applies retry + backoff, and translates the
    ccxt response back to an ``OrderEvent`` with the canonical fields
    populated. Off-line / not-configured behaviour falls back to
    rejecting the order with a clear status and no network call.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        market_type: str = "future",
        sandbox: Optional[bool] = None,
        rate_limit_ms: int = 200,
        max_retries: int = 3,
    ):
        self.api_key = api_key if api_key is not None else settings.exchange.api_key
        self.api_secret = api_secret if api_secret is not None else settings.exchange.api_secret
        self.market_type = market_type
        if sandbox is None:
            sandbox = settings.exchange.testnet
        self.sandbox = sandbox
        self.rate_limit_ms = rate_limit_ms
        self.max_retries = max_retries
        self._exchange: Optional[Any] = None
        self._closed = False

    def _ensure_exchange(self) -> Any:
        if ccxt_async is None:
            raise RuntimeError(f"ccxt is not installed: {_IMPORT_ERROR}")
        if self._exchange is not None:
            return self._exchange
        cls = getattr(ccxt_async, "binance")
        options: Dict[str, Any] = {
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
                logger.warning("Binance close failed: %s", exc)
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

    def _map_order_type(self, type_: OrderType) -> str:
        return {
            OrderType.MARKET: "market",
            OrderType.LIMIT: "limit",
            OrderType.STOP_LOSS: "stop_market",
            OrderType.STOP_LOSS_LIMIT: "stop",
            OrderType.TAKE_PROFIT: "take_profit_market",
            OrderType.TAKE_PROFIT_LIMIT: "take_profit",
            OrderType.LIMIT_MAKER: "limit_maker",
        }.get(type_, "limit")

    def _map_side(self, side: OrderSide) -> str:
        return "buy" if side == OrderSide.BUY else "sell"

    def _map_symbol(self, symbol: str) -> str:
        if "/" in symbol:
            return symbol
        if symbol.endswith("USDT"):
            base = symbol[: -len("USDT")]
            return f"{base}/USDT"
        return symbol

    async def submit_order(self, order: OrderEvent) -> OrderEvent:
        if not self._has_credentials(self.api_key, self.api_secret):
            return self._reject(
                order,
                OrderStatus.REJECTED,
                "Binance credentials missing; set BINANCE_API_KEY and BINANCE_API_SECRET",
            )
        if ccxt_async is None:
            return self._reject(order, OrderStatus.REJECTED, f"ccxt not installed: {_IMPORT_ERROR}")

        exchange = self._ensure_exchange()
        symbol = self._map_symbol(order.symbol)
        side = self._map_side(order.side)
        type_ = self._map_order_type(order.type)
        amount = float(order.quantity)

        params: Dict[str, Any] = {"type": self.market_type}
        if order.client_order_id:
            params["newClientOrderId"] = order.client_order_id
        if order.reduce_only:
            params["reduceOnly"] = True

        params_typed: Mapping[str, Any] = params

        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries):
            start = time.perf_counter()
            try:
                price: Optional[float] = None
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
                    "Binance submit_order failed (attempt %d/%d): %s. Retrying in %.1fs",
                    attempt + 1, self.max_retries, exc, backoff,
                )
                await asyncio.sleep(backoff)

        return self._reject(order, OrderStatus.REJECTED, str(last_exc) if last_exc else "submit failed")

    @staticmethod
    def _record_round_trip(order_type: str, start: float) -> None:
        latency_ms = (time.perf_counter() - start) * 1000.0
        try:
            from cryptobot.monitoring.metrics import record_execution_latency
            record_execution_latency(venue="binance", symbol="-", order_type=order_type, latency=latency_ms / 1000.0)
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
            logger.warning("Binance apply_fill parsing error: %s; raw=%s", exc, raw)
            order.status = OrderStatus.FILLED if order.filled_quantity > 0 else OrderStatus.NEW

        order.__post_init__()
        return order

    async def cancel_order(self, order_id: str) -> bool:
        if ccxt_async is None or not self._has_credentials(self.api_key, self.api_secret):
            return False
        exchange = self._ensure_exchange()
        try:
            await exchange.cancel_order(order_id)
            return True
        except Exception as exc:
            logger.warning("Binance cancel_order failed for %s: %s", order_id, exc)
            return False

    async def get_price(self, symbol: str) -> Decimal:
        if ccxt_async is None or not self._has_credentials(self.api_key, self.api_secret):
            return Decimal("0")
        exchange = self._ensure_exchange()
        start = time.perf_counter()
        try:
            mapped = self._map_symbol(symbol)
            ticker = await exchange.fetch_ticker(mapped)
            self._record_round_trip("quote", start)
            last = ticker.get("last") or ticker.get("close")
            return Decimal(str(last)) if last is not None else Decimal("0")
        except Exception as exc:
            logger.warning("Binance get_price failed: %s", exc)
            return Decimal("0")


__all__ = ["BinanceVenue"]
