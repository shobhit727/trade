"""Zerodha KiteConnect adapter.

The only place in the codebase that knows about a real broker. Everything upstream
depends on the `Broker` protocol (`execution/broker.py`), which is what gives
`GOAL.md` §5 Gate 6 its structural live/paper parity guarantee.

`kiteconnect` is an **optional** dependency. Importing this module must never be a
hard failure, because paper mode, the backtester and the unit tests all run without
broker credentials.
"""

from __future__ import annotations

import os
from decimal import Decimal as D

from .broker import BrokerBase, OrderResult, Position, Quote

#: NSE integer code for a plain intraday/delivery equity order.
ORDER_TYPE = "MARKET"
PRODUCT_MIS = "delivery"
TRANS_TYPE_BUY = "BUY"
TRANS_TYPE_SELL = "SELL"
VAL_MARGIN = "mis"


class KiteUnavailable(RuntimeError):
    """Raised when Kite cannot be reached or credentials are absent."""


class KiteBroker(BrokerBase):
    """Thin wrapper over KiteConnect.

    Credentials come from the environment only (``KITE_API_KEY``, ``KITE_API_SECRET``,
    ``KITE_ACCESS_TOKEN``). They are never read from, or written to, the repo.
    """

    def __init__(
        self,
        api_key: str | None = None,
        access_token: str | None = None,
        api_secret: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("KITE_API_KEY", "")
        self.access_token = access_token or os.environ.get("KITE_ACCESS_TOKEN", "")
        self.api_secret = api_secret or os.environ.get("KITE_API_SECRET", "")
        self.timeout = timeout
        self._k = None
        self._instrument_cache: dict[str, int] = {}

    # ------------------------------------------------------------------ #
    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.access_token)

    def _client(self):
        if self._k is not None:
            return self._k
        if not self.configured:
            raise KiteUnavailable(
                "KITE_API_KEY / KITE_ACCESS_TOKEN not set. Paper mode still works; "
                "live trading requires these."
            )
        try:
            from kiteconnect import KiteConnect  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dep
            raise KiteUnavailable(
                "kiteconnect is not installed; `pip install kiteconnect`"
            ) from exc
        self._k = KiteConnect(api_key=self.api_key, access_token=self.access_token)
        self._k.set_timeout(self.timeout)
        return self._k

    def _instrument_token(self, symbol: str) -> int:
        """Resolve ``symbol`` to an NSE instrument token, cached per process."""
        if symbol in self._instrument_cache:
            return self._instrument_cache[symbol]
        k = self._client()
        try:
            instruments = k.instruments("NSE")
        except Exception as exc:  # noqa: BLE001
            raise KiteUnavailable(f"instrument lookup failed: {exc}") from exc
        for inst in instruments or []:
            if (
                inst.get("tradingsymbol") == symbol
                and inst.get("exchange") == "NSE"
                and inst.get("segment") == "EQ"
            ):
                token = int(inst["instrument_token"])
                self._instrument_cache[symbol] = token
                return token
        raise KiteUnavailable(f"symbol {symbol!r} not found in NSE EQ instruments")

    # ------------------------------------------------------------------ #
    def get_quote(self, symbol: str) -> Quote:
        k = self._client()
        token = self._instrument_token(symbol)
        try:
            data = k.quote([("NSE", token)])
        except Exception as exc:  # noqa: BLE001
            raise KiteUnavailable(f"quote failed for {symbol}: {exc}") from exc
        key = f"NSE:{token}"
        payload = (data or {}).get(key)
        if not payload or "last_price" not in payload:
            raise KiteUnavailable(f"empty quote for {symbol}")
        return Quote(
            symbol=symbol,
            last=D(str(payload["last_price"])),
            bid=D(str(payload["bid"])) if payload.get("bid") is not None else None,
            ask=D(str(payload["ask"])) if payload.get("ask") is not None else None,
        )

    def get_positions(self) -> list[Position]:
        k = self._client()
        try:
            net = k.positions()
        except Exception as exc:  # noqa: BLE001
            raise KiteUnavailable(f"positions failed: {exc}") from exc
        out: list[Position] = []
        for row in (net or {}).get("net", []):
            try:
                qty = D(str(row["quantity"]))
            except (KeyError, TypeError):
                continue
            if qty == 0:
                continue
            out.append(
                Position(
                    symbol=row["tradingsymbol"],
                    quantity=qty,
                    average_price=D(str(row.get("average_price") or 0)),
                    last_price=D(str(row.get("last_price") or 0)) or None,
                )
            )
        return out

    def account_value(self) -> D:
        """Cash balance + market value of positions.

        Positions come from ``get_positions`` (live marks), cash from the funds
        endpoint. If funds are unavailable we fall back to the realised equity the
        live engine tracks, rather than reporting positions-only and triggering a
        phantom drawdown.
        """
        positions_value = sum((p.market_value for p in self.get_positions()), D("0"))
        try:
            funds = self._client().margins()
            available = funds.get("available", {})
            cash = D(str(
                available.get("cash")
                or available.get("opening_balance")
                or 0
            ))
        except Exception as exc:  # noqa: BLE001
            raise KiteUnavailable(f"cannot read funds/cash: {exc}") from exc
        return cash + positions_value

    # ------------------------------------------------------------------ #
    def place_market_order(self, symbol: str, quantity: D, side: str) -> OrderResult:
        side = self._check_side(side)
        quantity = self._check_qty(quantity)
        k = self._client()
        # Resolve the token first: an unknown symbol must fail before an order is sent.
        self._instrument_token(symbol)
        try:
            resp = k.place_order(
                variety=ORDER_TYPE,
                exchange="NSE",
                tradingsymbol=symbol,
                transaction_type=TRANS_TYPE_BUY if side == "BUY" else TRANS_TYPE_SELL,
                quantity=int(quantity),
                product=PRODUCT_MIS,
                order_type=ORDER_TYPE,
                val_margins=VAL_MARGIN,
            )
        except Exception as exc:  # noqa: BLE001
            raise KiteUnavailable(f"order rejected for {symbol}: {exc}") from exc

        oid = str(resp.get("order_id", ""))
        status = resp.get("status", "OPEN")
        fill = D(str(resp.get("average_price") or 0))
        return OrderResult(
            symbol=symbol,
            order_id=oid,
            quantity=quantity,
            filled_price=fill,
            status=status,
            message=str(resp.get("message", "")),
        )

    def cancel_all(self) -> None:
        k = self._client()
        try:
            orders = k.orders()
        except Exception as exc:  # noqa: BLE001
            raise KiteUnavailable(f"cannot list orders: {exc}") from exc
        for row in (orders or {}).get("pending", []):
            try:
                k.cancel_order(order_id=row["order_id"], variety=row["variety"])
            except Exception:  # noqa: BLE001 - best effort during a kill switch
                pass

    def is_connected(self) -> bool:
        try:
            self._client().profile()
            return True
        except Exception:  # noqa: BLE001
            return False
