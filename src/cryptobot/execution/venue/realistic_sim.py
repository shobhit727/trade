"""Realistic paper-trading venue: models what a retail algo actually faces.

Extends SimulatedVenue with the frictions that kill naive backtests:

- **Latency**: every order takes ``latency_ms`` (network + broker + exchange)
  before it can fill; fills price at the mark *after* the delay, not at
  submit time.
- **Partial fills**: a market order consumes book liquidity — capped at
  ``max_participation`` of recent bar volume, remainder stays open and
  fills over subsequent ticks up to ``partial_fill_bars``.
- **Size-based slippage**: impact grows with order size relative to
  participation cap (square-root-ish via linear ramp to ``impact_mult``).
- **Queue-aware limits**: resting limit orders only fill when price trades
  THROUGH them by ``queue_ticks`` ticks — being at the front of the queue
  is never assumed.

All knobs have honest defaults for a retail API on liquid Nifty50 names.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from decimal import Decimal

from cryptobot.core.events import OrderEvent, OrderStatus
from cryptobot.execution.venue.simulated import SimulatedVenue

logger = logging.getLogger(__name__)


@dataclass
class RealisticConfig:
    latency_ms: int = 150                 # one-way submit->exchange
    max_participation: float = 0.02       # max 2% of reference volume per order
    partial_fill_bars: int = 3            # bars over which the rest fills
    impact_mult: float = 3.0              # extra slippage multiplier at cap
    queue_ticks: int = 1                  # limit must be traded through by N ticks
    tick_size: Decimal = Decimal("0.05")  # NSE tick grid
    seed: int = 42


@dataclass
class _OpenRemainder:
    order_id: str
    qty: Decimal
    side: str
    bars_left: int


class RealisticSimVenue(SimulatedVenue):
    """SimulatedVenue + latency, partial fills, impact slippage, queue."""

    def __init__(self, prices=None, commission_bps: Decimal = Decimal("2"),
                 slippage_bps: Decimal = Decimal("1"),
                 maker_commission_bps: Decimal | None = None,
                 config: RealisticConfig | None = None):
        super().__init__(prices=prices or {}, slippage_bps=slippage_bps,
                         commission_bps=commission_bps,
                         maker_commission_bps=maker_commission_bps)
        self.cfg = config or RealisticConfig()
        self._rng = random.Random(self.cfg.seed)
        self._pending: list[dict] = []      # orders waiting out latency
        self._remainders: dict[str, _OpenRemainder] = {}
        self._reference_volume: dict[str, float] = {}
        self.stats = {"delayed": 0, "partials": 0, "impact_fills": 0,
                      "queue_rejects": 0}

    # ------------------------------------------------------------- plumbing

    def set_reference_volume(self, symbol: str, volume: float) -> None:
        """Caller (trader/backtester) feeds recent bar volume per symbol."""
        if volume > 0:
            self._reference_volume[symbol] = volume

    def _impact_slip(self, qty: Decimal, symbol: str) -> Decimal:
        ref = self._reference_volume.get(symbol, 0.0)
        cap_qty = ref * self.cfg.max_participation
        if cap_qty <= 0 or qty <= 0:
            return Decimal("0")
        ratio = min(float(qty) / cap_qty, 1.0)
        return Decimal(str(round(self.cfg.impact_mult * ratio * 10, 4)))  # bps

    def _quantize(self, px) -> Decimal:
        px = Decimal(str(px))
        t = self.cfg.tick_size
        return (px / t).quantize(Decimal("1")) * t

    # ---------------------------------------------------------------- venue

    async def submit_order(self, order: OrderEvent) -> OrderEvent:
        # Stage 1: latency queue — nothing fills before latency_ms elapses.
        self.stats["delayed"] += 1
        await self._sleep_latency()
        return await self._execute(order)

    async def _sleep_latency(self) -> None:
        import asyncio
        await asyncio.sleep(self.cfg.latency_ms / 1000.0)

    async def _execute(self, order: OrderEvent) -> OrderEvent:
        # Mark ALWAYS comes from the venue book; order.price is a LIMIT's
        # price tag (string payload), never the market reference.
        mark = self.prices.get(order.symbol, Decimal("0"))
        limit_px = Decimal(str(order.price)) if order.price else None
        if mark <= 0:
            order.status = OrderStatus.REJECTED
            order.__post_init__()
            order.payload["error"] = f"no positive mark for {order.symbol}"
            self.orders[order.order_id] = order
            return order

        is_maker = order.type.value == "LIMIT"
        fee_bps = (self.maker_commission_bps if is_maker else self.commission_bps)

        if is_maker:
            # Queue-aware: only fill if price trades THROUGH by queue_ticks.
            through = self.cfg.queue_ticks * self.cfg.tick_size
            limit_px = limit_px or mark
            crossed = ((mark - through) >= limit_px if order.side.value == "SELL"
                       else (mark + through) <= limit_px)
            if not crossed:
                self.stats["queue_rejects"] += 1
                order.status = OrderStatus.REJECTED
                order.__post_init__()
                order.payload["error"] = "limit not traded through (queue)"
                self.orders[order.order_id] = order
                return order
            fill_px = self._quantize(limit_px)
            slip = Decimal("0")
        else:
            slip = self.default_slippage_bps + self._impact_slip(order.quantity, order.symbol)
            if slip > self.default_slippage_bps:
                self.stats["impact_fills"] += 1
            direction = Decimal("1") if order.side.value == "BUY" else Decimal("-1")
            fill_px = self._quantize(mark * (Decimal("1") + direction * slip / Decimal("10000")))

        # Partial fills vs liquidity cap.
        ref = self._reference_volume.get(order.symbol, 0.0)
        cap_qty = Decimal(str(ref * self.cfg.max_participation)) if ref > 0 else order.quantity
        fill_qty = min(order.quantity, cap_qty)
        if fill_qty < order.quantity:
            self.stats["partials"] += 1
            self._remainders[order.order_id] = _OpenRemainder(
                order.order_id, order.quantity - fill_qty,
                order.side.value, self.cfg.partial_fill_bars)

        fees = (fill_qty * fill_px * fee_bps / Decimal("10000")).quantize(Decimal("0.0001"))
        order.filled_quantity = fill_qty
        order.avg_fill_price = fill_px
        order.commission = fees
        order.status = OrderStatus.PARTIALLY_FILLED if fill_qty < order.quantity else OrderStatus.FILLED
        order.__post_init__()
        self.orders[order.order_id] = order
        pos = self._position_qty.get(order.symbol, Decimal("0"))
        signed = fill_qty if order.side.value == "BUY" else -fill_qty
        self._position_qty[order.symbol] = pos + signed
        return order

    def advance_bar(self, symbol: str, close: Decimal, volume: float) -> list[OrderEvent]:
        """Called once per new bar: drip-fill remainders, refresh volume ref.

        Returns newly completed fills so the caller can update books.
        """
        self.set_reference_volume(symbol, volume)
        completed: list[OrderEvent] = []
        for rid, rem in list(self._remainders.items()):
            parent = self.orders.get(rid)
            if parent is None:
                self._remainders.pop(rid, None)
                continue
            step = min(rem.qty, Decimal(str(parent.filled_quantity)) or rem.qty)
            px = self._quantize(close)
            fees = (step * px * self.commission_bps / Decimal("10000")).quantize(Decimal("0.0001"))
            parent.commission += fees
            parent.avg_fill_price = ((parent.avg_fill_price * parent.filled_quantity + px * step)
                                     / (parent.filled_quantity + step))
            parent.filled_quantity += step
            rem.qty -= step
            rem.bars_left -= 1
            signed = step if rem.side == "BUY" else -step
            self._position_qty[symbol] = self._position_qty.get(symbol, Decimal("0")) + signed
            if rem.qty <= 0 or rem.bars_left <= 0:
                parent.status = OrderStatus.FILLED
                self._remainders.pop(rid, None)
            completed.append(parent)
        return completed
