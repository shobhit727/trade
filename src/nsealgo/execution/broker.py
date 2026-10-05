"""Broker abstraction — one interface, two implementations.

`GOAL.md` §5 Gate 6 requires that **live and paper share one code path** and differ
*only* in the broker adapter. `PaperBroker` and `KiteBroker` both implement `Broker`,
and the live engine holds a `Broker` — it has no idea which it is talking to. That is
what makes the parity claim structural rather than aspirational.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from decimal import Decimal as D
from typing import Protocol


@dataclass(frozen=True)
class Quote:
    symbol: str
    last: D
    bid: D | None = None
    ask: D | None = None

    @property
    def mid(self) -> D:
        if self.bid is not None and self.ask is not None:
            return (self.bid + self.ask) / 2
        return self.last


@dataclass(frozen=True)
class Position:
    symbol: str
    quantity: D
    average_price: D
    last_price: D | None = None

    @property
    def market_value(self) -> D:
        px = self.last_price if self.last_price is not None else self.average_price
        return self.quantity * px

    @property
    def unrealised_pnl(self) -> D:
        px = self.last_price if self.last_price is not None else self.average_price
        return (px - self.average_price) * self.quantity


@dataclass(frozen=True)
class OrderResult:
    symbol: str
    order_id: str
    quantity: D
    filled_price: D
    status: str  # "COMPLETE" | "OPEN" | "REJECTED"
    message: str = ""


class Broker(Protocol):
    """The entire surface the strategy engine is allowed to use."""

    def get_quote(self, symbol: str) -> Quote: ...
    def get_positions(self) -> list[Position]: ...
    def account_value(self) -> D:
        """**Total** account value: cash + market value of all positions.

        Not just positions. A book that is 30% invested in equities is not down 70%.
        """
    def place_market_order(self, symbol: str, quantity: D, side: str) -> OrderResult: ...
    def cancel_all(self) -> None: ...
    def is_connected(self) -> bool: ...


class BrokerBase(abc.ABC):
    """Common validation shared by all adapters, so no adapter can skip it."""

    @staticmethod
    def _check_side(side: str) -> str:
        s = side.upper().strip()
        if s not in ("BUY", "SELL"):
            raise ValueError(f"side must be BUY or SELL, got {side!r}")
        return s

    @staticmethod
    def _check_qty(quantity: D) -> D:
        if quantity < 0:
            raise ValueError("quantity must be non-negative (long-only account)")
        return quantity

    @abc.abstractmethod
    def get_quote(self, symbol: str) -> Quote: ...

    @abc.abstractmethod
    def get_positions(self) -> list[Position]: ...

    @abc.abstractmethod
    def account_value(self) -> D:
        """Cash + positions. Must include cash."""

    @abc.abstractmethod
    def place_market_order(self, symbol: str, quantity: D, side: str) -> OrderResult: ...

    @abc.abstractmethod
    def cancel_all(self) -> None: ...

    @abc.abstractmethod
    def is_connected(self) -> bool: ...
