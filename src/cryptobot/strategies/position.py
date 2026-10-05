"""Position management primitives: scaling in/out, stops, trailing stops.

Strategies compose a :class:`PositionManager` to track open positions per
symbol and generate risk/exit :class:`OrderEvent` actions without duplicating
position math. Pure state — no I/O, no EventBus dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.core.events import OrderEvent, OrderSide, OrderType, PositionSide


@dataclass
class Position:
    """A single open position for one symbol."""

    symbol: str
    side: PositionSide
    quantity: Decimal = Decimal("0")
    avg_entry: Decimal = Decimal("0")
    stop_price: Decimal | None = None
    take_profit_price: Decimal | None = None
    highest_price: Decimal = Decimal("0")
    lowest_price: Decimal | None = None
    strategy: str = ""

    @property
    def is_open(self) -> bool:
        return self.quantity > 0

    @property
    def notional(self) -> Decimal:
        return self.quantity * self.avg_entry


class PositionManager:
    """Tracks positions per symbol and derives exit/scaling orders."""

    def __init__(self):
        self._positions: dict[str, Position] = {}

    def get(self, symbol: str) -> Position | None:
        return self._positions.get(symbol)

    def all(self) -> list[Position]:
        return [p for p in self._positions.values() if p.is_open]

    def apply_fill(self, order: OrderEvent) -> None:
        """Update position from a filled OrderEvent (entry, scale-in, scale-out, or close)."""
        qty = order.filled_quantity or order.quantity
        if qty <= 0 or order.avg_fill_price is None or order.avg_fill_price <= 0:
            return
        price = order.avg_fill_price
        pos = self._positions.setdefault(
            order.symbol,
            Position(symbol=order.symbol, side=order.position_side, strategy=order.strategy),
        )
        if pos.quantity == 0:
            pos.side = order.position_side
            if pos.side is PositionSide.BOTH:
                pos.side = PositionSide.LONG if order.side is OrderSide.BUY else PositionSide.SHORT
            pos.avg_entry = Decimal("0")
            pos.highest_price = Decimal("0")
            pos.lowest_price = None

        # Does this fill grow the position?
        increases = (
            order.side is OrderSide.BUY if pos.side is PositionSide.LONG else order.side is OrderSide.SELL
        )
        if increases:
            old_notional = pos.quantity * pos.avg_entry
            pos.quantity += qty
            pos.avg_entry = (old_notional + qty * price) / pos.quantity
        else:
            remaining = pos.quantity - qty
            if remaining <= 0:
                pos.quantity = Decimal("0")
                pos.avg_entry = Decimal("0")
            else:
                pos.quantity = remaining
        self._update_extremes(pos, price)

    def set_stop(self, symbol: str, price: Decimal) -> None:
        pos = self._positions.get(symbol)
        if pos is not None:
            pos.stop_price = price

    def set_take_profit(self, symbol: str, price: Decimal) -> None:
        pos = self._positions.get(symbol)
        if pos is not None:
            pos.take_profit_price = price

    def update_trailing_stop(self, symbol: str, current_price: Decimal, trail_pct: Decimal) -> Decimal | None:
        """Ratchet a trailing stop behind price; returns new stop (or None if unchanged)."""
        pos = self._positions.get(symbol)
        if pos is None or not pos.is_open or trail_pct <= 0:
            return None
        self._update_extremes(pos, current_price)
        if pos.side is PositionSide.LONG:
            new_stop = pos.highest_price * (Decimal("1") - trail_pct)
            if pos.stop_price is None or new_stop > pos.stop_price:
                pos.stop_price = new_stop
                return new_stop
        else:
            low = pos.lowest_price if pos.lowest_price else current_price
            new_stop = low * (Decimal("1") + trail_pct)
            if pos.stop_price is None or new_stop < pos.stop_price:
                pos.stop_price = new_stop
                return new_stop
        return None

    def stop_exit_order(self, symbol: str) -> OrderEvent | None:
        """Build a stop-loss OrderEvent from the tracked stop price."""
        pos = self._positions.get(symbol)
        if pos is None or not pos.is_open or pos.stop_price is None:
            return None
        side = OrderSide.SELL if pos.side is PositionSide.LONG else OrderSide.BUY
        return OrderEvent(
            symbol=symbol,
            side=side,
            type=OrderType.STOP_LOSS,
            quantity=pos.quantity,
            stop_price=pos.stop_price,
            reduce_only=True,
            position_side=pos.side,
            strategy=pos.strategy,
        )

    def take_profit_order(self, symbol: str) -> OrderEvent | None:
        pos = self._positions.get(symbol)
        if pos is None or not pos.is_open or pos.take_profit_price is None:
            return None
        side = OrderSide.SELL if pos.side is PositionSide.LONG else OrderSide.BUY
        return OrderEvent(
            symbol=symbol,
            side=side,
            type=OrderType.TAKE_PROFIT,
            quantity=pos.quantity,
            price=pos.take_profit_price,
            reduce_only=True,
            position_side=pos.side,
            strategy=pos.strategy,
        )

    def _update_extremes(self, pos: Position, price: Decimal) -> None:
        pos.highest_price = max(pos.highest_price, price)
        pos.lowest_price = price if pos.lowest_price is None else min(pos.lowest_price, price)


__all__ = ["Position", "PositionManager"]
