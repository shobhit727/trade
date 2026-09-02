"""Zerodha Kite Connect venue — real NSE orders behind the Venue protocol.

Auth model (Kite has no permanent keys):
    1. Owner opens the login URL (api_key needed) and logs in; Kite
       redirects with ?request_token=...
    2. `tools/kite_login.py --request-token T` exchanges it for an
       access_token (checksum = sha256(api_key + request_token + api_secret))
       and stores it in state-nse/kite_session.json.
    3. The venue reads that token per request. Tokens expire daily (~6am IST)
       -> re-login each morning before market open.

Order mapping:
    Market/Limit, BUY/SELL map 1:1 to Kite regular orders on exchange=NSE,
    product=DELIVERY (CNC) for the basket's long-only delivery holdings.
    Fills are NOT pushed by REST: submit_order places the order and polls
    order status until complete/rejected (Kite reports avg. fill price).

Dry-run mode (default until explicitly enabled): every call is logged and
returns a synthetic FILLED ack without touching Kite — lets the whole
pipeline be exercised end-to-end before real money.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal
from pathlib import Path

from cryptobot.config import get_settings
from cryptobot.core.events import OrderEvent, OrderStatus
from cryptobot.execution.venue.base import Venue

logger = logging.getLogger(__name__)

SESSION_FILE = Path("state-nse/kite_session.json")


def _get_kite_base() -> str:
    return get_settings().external_services.kite_base_url


def _get_kite_login_url() -> str:
    return get_settings().external_services.kite_login_url


def _get_http_default_timeout() -> int:
    return get_settings().timeouts.http_default_timeout


class KiteSession:
    """Holds api_key + access_token; performs the token exchange."""

    def __init__(self, api_key: str, api_secret: str = "",
                 session_file: Path = SESSION_FILE):
        self.api_key = api_key
        self.api_secret = api_secret
        self.session_file = session_file
        self.access_token: str | None = None
        if session_file.exists():
            self.access_token = json.loads(session_file.read_text()).get("access_token")

    def login_url(self) -> str:
        return (f"{_get_kite_login_url()}?v=3&api_key={self.api_key}")

    def exchange_token(self, request_token: str) -> str:
        checksum = hashlib.sha256(
            f"{self.api_key}{request_token}{self.api_secret}".encode()
        ).hexdigest()
        data = urllib.parse.urlencode({
            "api_key": self.api_key, "request_token": request_token,
            "checksum": checksum,
        }).encode()
        req = urllib.request.Request(
            f"{_get_kite_base()}/session/token", data=data, method="POST",
            headers={"X-Kite-Version": "3"})
        with urllib.request.urlopen(req, timeout=_get_http_default_timeout()) as r:
            payload = json.load(r)
        self.access_token = payload["data"]["access_token"]
        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        self.session_file.write_text(json.dumps({
            "access_token": self.access_token,
            "user_id": payload["data"].get("user_id"),
            "issued_at": int(time.time()),
        }))
        return self.access_token

    def headers(self) -> dict:
        if not self.access_token:
            raise RuntimeError(
                "Kite access token missing — run tools/kite_login.py after "
                f"opening {self.login_url()}")
        return {"X-Kite-Version": "3",
                "Authorization": f"token {self.api_key}:{self.access_token}",
                "Content-Type": "application/x-www-form-urlencoded"}


class KiteVenue(Venue):
    """Real-order NSE venue. dry_run=True never sends anything."""

    def __init__(self, session: KiteSession, dry_run: bool = True,
                 product: str = "CNC", poll_seconds: float = 1.0,
                 poll_timeout: float = 60.0):
        self.session = session
        self.dry_run = dry_run
        self.product = product            # CNC delivery / MIS intraday
        self.poll_seconds = poll_seconds
        self.poll_timeout = poll_timeout
        self.prices: dict[str, Decimal] = {}
        self.orders: dict[str, OrderEvent] = {}

    # ------------------------------------------------------------- plumbing

    def _request(self, path: str, params: dict | None = None,
                 method: str = "GET") -> dict:
        url = f"{_get_kite_base()}{path}"
        data = urllib.parse.urlencode(params).encode() if params else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers=self.session.headers())
        try:
            with urllib.request.urlopen(req, timeout=_get_http_default_timeout()) as r:
                out = json.load(r)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode()[:200]
            raise RuntimeError(f"kite {path} -> HTTP {exc.code}: {body}") from exc
        if not out.get("status") == "success":
            raise RuntimeError(f"kite {path} error: {out}")
        return out.get("data", {})

    @staticmethod
    def _qty(order: OrderEvent) -> str:
        return str(max(1, int(abs(Decimal(str(order.quantity))))))

    # ------------------------------------------------------------ Venue API

    async def submit_order(self, order: OrderEvent) -> OrderEvent:
        qty = self._qty(order)
        params = {
            "tradingsymbol": order.symbol,
            "exchange": "NSE",
            "transaction_type": order.side.value,
            "order_type": "LIMIT" if order.type.value == "LIMIT" else "MARKET",
            "quantity": qty,
            "product": self.product,
            "validity": "DAY",
        }
        if params["order_type"] == "LIMIT":
            params["price"] = str(round(float(Decimal(str(order.price))), 2))

        if self.dry_run:
            logger.warning("KITE DRY-RUN %s %s x%s @%s",
                           order.side.value, order.symbol, qty,
                           params.get("price", "MKT"))
            order.filled_quantity = Decimal(qty)
            order.avg_fill_price = Decimal(str(params.get("price")
                                               or self.prices.get(order.symbol, "0")))
            order.commission = Decimal("0")
            order.status = OrderStatus.FILLED
            order.__post_init__()
            order.payload["dry_run"] = True
            self.orders[order.order_id] = order
            return order

        try:
            resp = self._request("/orders/regular", params, method="POST")
        except Exception as exc:  # noqa: BLE001
            order.status = OrderStatus.REJECTED
            order.__post_init__()
            order.payload["error"] = str(exc)[:180]
            self.orders[order.order_id] = order
            return order

        order_id = resp["order_id"]
        deadline = time.monotonic() + self.poll_timeout
        while time.monotonic() < deadline:
            await asyncio.sleep(self.poll_seconds)
            try:
                history = self._request(f"/orders/regular/{order_id}")
            except Exception as exc:  # noqa: BLE001  # transient — keep polling
                logger.warning("kite poll failed: %s", exc)
                continue
            entry = history[-1] if isinstance(history, list) else history
            status = str(entry.get("status", "")).upper()
            filled = Decimal(str(entry.get("filled_quantity") or 0))
            if status in ("COMPLETE", "REJECTED", "CANCELLED"):
                order.filled_quantity = filled
                order.avg_fill_price = Decimal(str(entry.get("average_price") or 0))
                order.status = (OrderStatus.FILLED if status == "COMPLETE"
                                else OrderStatus.REJECTED)
                break
            if filled > 0:
                order.status = OrderStatus.PARTIALLY_FILLED
                order.filled_quantity = filled
        else:
            order.status = OrderStatus.REJECTED
            order.payload["error"] = "poll timeout"
        order.__post_init__()
        # __post_init__ normalises/rebuilds payload — attach broker refs last.
        order.payload["kite_order_id"] = order_id
        if status != "COMPLETE":
            order.payload["error"] = str(entry.get("status_message") or status)
        self.orders[order.order_id] = order
        return order

    async def cancel_order(self, order_id: str) -> bool:
        if self.dry_run:
            return True
        try:
            self._request(f"/orders/regular/{order_id}", method="DELETE")
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("kite cancel %s failed: %s", order_id, exc)
            return False

    async def get_price(self, symbol: str) -> Decimal:
        if symbol in self.prices:
            return self.prices[symbol]
        if self.dry_run:
            return Decimal("0")
        # LTP quote endpoint accepts comma-separated instruments.
        data = self._request("/quote/ltp", {"i": f"NSE:{symbol}"})
        ltp = data.get(f"NSE:{symbol}", {}).get("last_price")
        px = Decimal(str(ltp or 0))
        self.prices[symbol] = px
        return px
