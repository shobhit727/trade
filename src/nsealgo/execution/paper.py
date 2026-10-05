"""Paper broker — simulated fills, but with the *real* cost stack.

`GOAL.md` §5 Gate 6: paper and live must share one code path. The only differences here
versus `KiteBroker` are:

1. fills are simulated at a supplied price rather than fetched from the exchange, and
2. no orders leave the process.

Everything the strategy can observe — cash, positions, average price, order lifecycle —
is modelled, and **costs are charged from `nsealgo.costs.CostModel`**, so a paper run
is not silently a zero-cost fantasy.
"""

from __future__ import annotations

import itertools
from decimal import Decimal as D

from ..costs import CostModel
from .broker import BrokerBase, OrderResult, Position, Quote


class PaperBroker(BrokerBase):
    """In-memory simulated broker with realistic fills and full Indian costs."""

    def __init__(
        self,
        capital: D = D("2100000"),
        cost_model: CostModel | None = None,
        price_source=None,
    ) -> None:
        self.capital = capital
        self.cash = capital
        self.cost_model = cost_model or CostModel(segment="delivery")
        #: Callable(symbol) -> D, supplied by the engine so paper and live read the
        #: same price stream. If None, orders fill at last quoted price.
        self.price_source = price_source
        self._positions: dict[str, Position] = {}
        self._quotes: dict[str, Quote] = {}
        self._ids = itertools.count(1)
        self.total_costs = D("0")

    # ------------------------------------------------------------------ #
    def set_quote(self, quote: Quote) -> None:
        """Feed a quote in. The engine does this from the same data feed it uses live."""
        self._quotes[quote.symbol] = quote
        if quote.symbol in self._positions:
            p = self._positions[quote.symbol]
            self._positions[quote.symbol] = Position(
                p.symbol, p.quantity, p.average_price, quote.last
            )

    def _price(self, symbol: str) -> D:
        if self.price_source is not None:
            return D(str(self.price_source(symbol)))
        q = self._quotes.get(symbol)
        if q is None:
            raise KeyError(f"no quote for {symbol}; call set_quote() first")
        return q.last

    # ------------------------------------------------------------------ #
    def get_quote(self, symbol: str) -> Quote:
        q = self._quotes.get(symbol)
        if q is not None:
            return q
        # No explicit quote: fall back to the price source so the engine can trade
        # against the same price stream the factors were computed from.
        return Quote(symbol, self._price(symbol))

    def get_positions(self) -> list[Position]:
        return list(self._positions.values())

    def is_connected(self) -> bool:
        return True

    # ------------------------------------------------------------------ #
    def place_market_order(self, symbol: str, quantity: D, side: str) -> OrderResult:
        side = self._check_side(side)
        quantity = self._check_qty(quantity)
        order_id = f"P{next(self._ids):08d}"

        if quantity == 0:
            return OrderResult(symbol, order_id, D("0"), D("0"), "REJECTED", "zero quantity")

        ref = self._price(symbol)
        fill = self.cost_model.fill_price(ref, side)
        bd = self.cost_model.cost(side, quantity, fill)
        self.total_costs += bd.total

        pos = self._positions.get(symbol)

        if side == "BUY":
            outlay = quantity * fill + bd.total
            if outlay > self.cash:
                return OrderResult(
                    symbol, order_id, quantity, fill, "REJECTED",
                    f"insufficient cash: need Rs {outlay:.2f}, have Rs {self.cash:.2f}",
                )
            self.cash -= outlay
            new_qty = (pos.quantity if pos else D("0")) + quantity
            new_avg = (
                (pos.average_price * pos.quantity + fill * quantity) / new_qty
                if pos and pos.quantity > 0
                else fill
            )
            self._positions[symbol] = Position(symbol, new_qty, new_avg, ref)
            return OrderResult(symbol, order_id, quantity, fill, "COMPLETE")

        # ---- SELL
        held = pos.quantity if pos else D("0")
        if quantity > held:
            return OrderResult(
                symbol, order_id, quantity, fill, "REJECTED",
                f"long-only: cannot sell {quantity}, only {held} held",
            )
        proceeds = quantity * fill - bd.total
        self.cash += proceeds
        remaining = held - quantity
        if remaining == 0:
            self._positions.pop(symbol, None)
        else:
            self._positions[symbol] = Position(symbol, remaining, pos.average_price, ref)
        return OrderResult(symbol, order_id, quantity, fill, "COMPLETE")

    # ------------------------------------------------------------------ #
    def cancel_all(self) -> None:
        """No-op: paper fills are instantaneous, so nothing is ever open."""
        return None

    # ------------------------------------------------------------------ #
    def account_value(self) -> D:
        """Cash + positions. This is the number the risk manager must see."""
        return self.cash + sum(p.market_value for p in self._positions.values())

    # Kept as a readable alias; both names mean the same thing.
    portfolio_value = account_value

    def equity_curve_point(self) -> D:
        """Equity as a rupee amount, for the risk manager."""
        return self.portfolio_value()

    def reconcile(self) -> list[tuple[str, D, D]]:
        """Return ``(symbol, paper_qty, expected_qty)`` diffs. Paper is self-consistent
        by construction, so this always returns empty — it exists so the *same*
        reconciliation code runs in paper and live."""
        return []
