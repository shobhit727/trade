from __future__ import annotations

import asyncio
import logging
import random
import time
from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from cryptobot.core.events import OrderEvent, OrderSide, OrderStatus, OrderType
from cryptobot.execution.venue.base import Venue

logger = logging.getLogger(__name__)


class OrderBookSide(Enum):
    BID = "bid"
    ASK = "ask"


@dataclass
class QueuePosition:
    """Represents an order's position in the queue at a price level."""
    order_id: str
    quantity: Decimal
    timestamp: float
    is_maker: bool = True


@dataclass
class PriceLevel:
    """A single price level in the order book with queue of orders."""
    price: Decimal
    side: OrderBookSide
    orders: deque = field(default_factory=deque)
    total_quantity: Decimal = Decimal("0")

    def add_order(self, order: QueuePosition) -> None:
        self.orders.append(order)
        self.total_quantity += order.quantity

    def remove_order(self, order_id: str) -> Decimal:
        for _, order in enumerate(self.orders):
            if order.order_id == order_id:
                qty = order.quantity
                self.orders.remove(order)
                self.total_quantity -= qty
                return qty
        return Decimal("0")

    def fill_quantity(self, qty: Decimal) -> list[tuple[str, Decimal]]:
        """Fill orders at this price level, returning list of (order_id, filled_qty)."""
        filled = []
        remaining = qty
        while remaining > 0 and self.orders:
            order = self.orders[0]
            if order.quantity <= remaining:
                filled.append((order.order_id, order.quantity))
                remaining -= order.quantity
                self.total_quantity -= order.quantity
                self.orders.popleft()
            else:
                filled.append((order.order_id, remaining))
                order.quantity -= remaining
                self.total_quantity -= remaining
                remaining = Decimal("0")
        return filled


@dataclass
class LatencyConfig:
    """Network and processing latency configuration."""
    base_latency_ms: float = 1.0
    latency_jitter_ms: float = 0.5
    processing_latency_ms: float = 0.1


@dataclass
class AdverseSelectionConfig:
    """Adverse selection modeling configuration."""
    enabled: bool = True
    toxicity_threshold: float = 0.1
    max_adverse_bps: Decimal = Decimal("10")
    decay_half_life_ms: float = 100.0


@dataclass
class QueueModelConfig:
    """Queue position and partial fill configuration."""
    enabled: bool = True
    min_fill_ratio: float = 0.1
    max_queue_position: int = 1000
    cancellation_rate_per_sec: float = 0.01


@dataclass
class RealisticVenueConfig:
    """Complete configuration for realistic venue."""
    # Market data
    initial_prices: dict[str, Decimal] = field(default_factory=dict)

    # Fee structure
    maker_fee_bps: Decimal = Decimal("1")
    taker_fee_bps: Decimal = Decimal("5")

    # Slippage
    base_slippage_bps: Decimal = Decimal("2")
    max_slippage_bps: Decimal = Decimal("50")

    # Funding
    funding_rate: Decimal = Decimal("0.0001")
    funding_interval_hours: int = 8

    # Latency
    latency: LatencyConfig = field(default_factory=LatencyConfig)

    # Adverse selection
    adverse_selection: AdverseSelectionConfig = field(default_factory=AdverseSelectionConfig)

    # Queue model
    queue_model: QueueModelConfig = field(default_factory=QueueModelConfig)

    # Market impact
    impact_coefficient: Decimal = Decimal("0.01")
    max_participation_rate: Decimal = Decimal("0.1")

    # Tick size
    tick_sizes: dict[str, Decimal] = field(default_factory=dict)


class OrderBookSimulator:
    """Simulates a realistic limit order book with queue positions."""

    def __init__(self, config: RealisticVenueConfig):
        self.config = config
        self.books: dict[str, dict[OrderBookSide, dict[Decimal, PriceLevel]]] = {}
        self.mid_prices: dict[str, Decimal] = {}
        self.spreads: dict[str, Decimal] = {}
        self.volatilities: dict[str, Decimal] = {}
        self.last_update: dict[str, float] = {}

    def initialize_symbol(self, symbol: str, mid_price: Decimal, spread: Decimal = Decimal("1"), tick_size: Decimal = Decimal("0.01")) -> None:
        """Initialize order book for a symbol."""
        self.mid_prices[symbol] = mid_price
        self.spreads[symbol] = spread
        self.volatilities[symbol] = Decimal("0.01")
        self.last_update[symbol] = time.time()

        # Create initial order book levels
        self.books[symbol] = {OrderBookSide.BID: {}, OrderBookSide.ASK: {}}

        half_spread = spread / Decimal("2")
        bid_start = mid_price - half_spread
        ask_start = mid_price + half_spread

        # Create multiple levels on each side
        for i in range(20):
            i_dec = Decimal(str(i))
            tick = Decimal(str(self.config.tick_sizes.get(symbol, Decimal("0.01"))))
            bid_price = (bid_start - i_dec * tick).quantize(Decimal("0.01"))
            ask_price = (ask_start + i_dec * tick).quantize(Decimal("0.01"))

            # Add liquidity - more at better prices (quantities kept for future use)
            _bid_qty = Decimal(str(random.uniform(10, 100))) * (Decimal("20") - i_dec) / Decimal("20")
            _ask_qty = Decimal(str(random.uniform(10, 100))) * (Decimal("20") - i_dec) / Decimal("20")

            self.books[symbol][OrderBookSide.BID][bid_price] = PriceLevel(price=bid_price, side=OrderBookSide.BID)
            self.books[symbol][OrderBookSide.ASK][ask_price] = PriceLevel(price=ask_price, side=OrderBookSide.ASK)

    def get_best_bid(self, symbol: str) -> Decimal | None:
        bids = self.books.get(symbol, {}).get(OrderBookSide.BID, {})
        if not bids:
            return None
        return max(bids.keys())

    def get_best_ask(self, symbol: str) -> Decimal | None:
        asks = self.books.get(symbol, {}).get(OrderBookSide.ASK, {})
        if not asks:
            return None
        return min(asks.keys())

    def get_mid_price(self, symbol: str) -> Decimal:
        return self.mid_prices.get(symbol, Decimal("0"))

    def get_spread(self, symbol: str) -> Decimal:
        bid = self.get_best_bid(symbol)
        ask = self.get_best_ask(symbol)
        if bid and ask:
            return ask - bid
        return self.spreads.get(symbol, Decimal("0"))

    def place_order(self, symbol: str, side: OrderSide, price: Decimal, quantity: Decimal, order_id: str) -> tuple[bool, Decimal]:
        """Place a limit order in the book. Returns (success, queue_position)."""
        if symbol not in self.books:
            return False, Decimal("0")

        book_side = OrderBookSide.BID if side == OrderSide.BUY else OrderBookSide.ASK
        book = self.books[symbol][book_side]

        # Find or create price level
        if price not in book:
            book[price] = PriceLevel(price=price, side=book_side)

        level = book[price]

        # Calculate queue position
        queue_position = sum(o.quantity for o in level.orders)

        # Create queue position
        qp = QueuePosition(
            order_id=order_id,
            quantity=quantity,
            timestamp=time.time(),
            is_maker=True
        )
        level.add_order(qp)

        return True, queue_position

    def cancel_order(self, symbol: str, side: OrderSide, price: Decimal, order_id: str) -> bool:
        """Cancel an order from the book."""
        if symbol not in self.books:
            return False

        book_side = OrderBookSide.BID if side == OrderSide.BUY else OrderBookSide.ASK
        book = self.books[symbol][book_side]

        if price not in book:
            return False

        level = book[price]
        removed = level.remove_order(order_id)
        return removed > 0

    def match_market_order(self, symbol: str, side: OrderSide, quantity: Decimal) -> list[tuple[Decimal, Decimal, bool]]:
        """Match a market order against the book. Returns list of (price, qty, is_maker)."""
        if symbol not in self.books:
            return []

        # Market buy hits asks, market sell hits bids
        book_side = OrderBookSide.ASK if side == OrderSide.BUY else OrderBookSide.BID
        book = self.books[symbol][book_side]

        if not book:
            return []

        fills = []
        remaining = quantity

        # Sort prices appropriately
        prices = sorted(book.keys(), reverse=(side == OrderSide.SELL))

        for price in prices:
            if remaining <= 0:
                break
            level = book[price]
            if level.total_quantity <= 0:
                continue

            fill_qty = min(remaining, level.total_quantity)
            level_fills = level.fill_quantity(fill_qty)

            for _, filled_qty in level_fills:
                fills.append((price, filled_qty, True))  # Maker fills
                remaining -= filled_qty

            # Clean up empty levels
            if level.total_quantity == 0:
                del book[price]

        return fills

    def update_mid_price(self, symbol: str, new_mid: Decimal, volatility: Decimal | None = None) -> None:
        """Update mid price and shift the book."""
        if symbol not in self.books:
            return

        old_mid = self.mid_prices[symbol]
        shift = new_mid - old_mid

        if abs(shift) < Decimal(str(self.config.tick_sizes.get(symbol, Decimal("0.01")))):
            return

        self.mid_prices[symbol] = new_mid
        if volatility is not None:
            self.volatilities[symbol] = volatility

        # Rebuild book around new mid
        spread = self.get_spread(symbol)
        half_spread = spread / Decimal("2")
        bid_start = new_mid - half_spread
        ask_start = new_mid + half_spread

        # Recreate book with new center
        self.books[symbol] = {OrderBookSide.BID: {}, OrderBookSide.ASK: {}}
        tick = Decimal(str(self.config.tick_sizes.get(symbol, Decimal("0.01"))))

        for i in range(20):
            bid_price = (bid_start - Decimal(str(i)) * tick).quantize(Decimal("0.01"))
            ask_price = (ask_start + Decimal(str(i)) * tick).quantize(Decimal("0.01"))

            _bid_qty = Decimal(str(random.uniform(10, 100))) * (Decimal("20") - Decimal(str(i))) / Decimal("20")
            _ask_qty = Decimal(str(random.uniform(10, 100))) * (Decimal("20") - Decimal(str(i))) / Decimal("20")

            self.books[symbol][OrderBookSide.BID][bid_price] = PriceLevel(price=bid_price, side=OrderBookSide.BID)
            self.books[symbol][OrderBookSide.ASK][ask_price] = PriceLevel(price=ask_price, side=OrderBookSide.ASK)


class RealisticVenue(Venue):
    """
    Realistic execution venue with:
    - Realistic order book with queue positions
    - Latency modeling
    - Partial fills based on queue position
    - Adverse selection
    - Maker/taker fee structure
    - Market impact
    """

    def __init__(self, config: RealisticVenueConfig | None = None):
        self.config = config or RealisticVenueConfig()
        self.book_sim = OrderBookSimulator(self.config)
        self.orders: dict[str, OrderEvent] = {}
        self._position_qty: dict[str, Decimal] = {}
        self._order_queue_info: dict[str, dict] = {}  # order_id -> {queue_pos, side, price, symbol}
        self._last_funding: dict[str, float] = {}
        self._latency_jitter: float = 0.0

        # Initialize symbols
        for symbol, price in self.config.initial_prices.items():
            tick = Decimal(str(self.config.tick_sizes.get(symbol, Decimal("0.01"))))
            spread = self.config.spreads.get(symbol, Decimal("1")) if hasattr(self.config, 'spreads') else Decimal("1")
            self.book_sim.initialize_symbol(symbol, price, spread, tick)
            self._last_funding[symbol] = time.time()

    def _simulate_latency(self) -> float:
        """Simulate network + processing latency."""
        base = self.config.latency.base_latency_ms
        jitter = random.uniform(-self.config.latency.latency_jitter_ms, self.config.latency.latency_jitter_ms)
        processing = self.config.latency.processing_latency_ms
        return (base + jitter + processing) / 1000.0  # Convert to seconds

    def _calculate_adverse_selection(self, symbol: str, side: OrderSide, fill_price: Decimal, mark_price: Decimal) -> Decimal:
        """Calculate adverse selection cost."""
        if not self.config.adverse_selection.enabled:
            return Decimal("0")

        # Simple adverse selection: price moves against you after fill
        volatility = self.book_sim.volatilities.get(symbol, Decimal("0.01"))
        time_horizon = Decimal("1")  # 1 second
        adverse_move = volatility * time_horizon * self.config.adverse_selection.max_adverse_bps / Decimal("10000")

        # Direction depends on side
        if side == OrderSide.BUY:
            adverse_price = fill_price - (mark_price * adverse_move)
        else:
            adverse_price = fill_price + (mark_price * adverse_move)

        return abs(fill_price - adverse_price)

    def _calculate_market_impact(self, symbol: str, side: OrderSide, quantity: Decimal, mark_price: Decimal) -> Decimal:
        """Calculate market impact cost."""
        # Linear impact model: impact = coefficient * participation_rate
        daily_volume = Decimal("1000000")  # Would come from real data
        participation = quantity / daily_volume if daily_volume > 0 else Decimal("0")
        participation = min(participation, self.config.max_participation_rate)

        impact = self.config.impact_coefficient * participation
        return mark_price * impact

    def _apply_slippage(self, mark_price: Decimal, side: OrderSide, slippage_bps: Decimal, quantity: Decimal, symbol: str) -> Decimal:
        """Apply slippage to mark price."""
        base_slip = slippage_bps / Decimal("10000")

        # Add market impact
        impact = self._calculate_market_impact(symbol, side, quantity, mark_price)
        impact_bps = (impact / mark_price * Decimal("10000")) if mark_price > 0 else Decimal("0")

        total_slip_bps = min(base_slip + impact_bps, self.config.max_slippage_bps / Decimal("10000"))

        if side == OrderSide.BUY:
            fill_price = mark_price * (Decimal("1") + total_slip_bps)
        else:
            fill_price = mark_price * (Decimal("1") - total_slip_bps)

        # Round to tick size
        tick = Decimal(str(self.config.tick_sizes.get(symbol, Decimal("0.01"))))
        fill_price = (fill_price / tick).quantize(Decimal("1")) * tick

        return fill_price

    async def submit_order(self, order: OrderEvent) -> OrderEvent:
        start = time.perf_counter()

        # Simulate latency
        latency = self._simulate_latency()
        await asyncio.sleep(latency)

        symbol = order.symbol
        mark_price = order.price or self.book_sim.get_mid_price(symbol)

        if mark_price <= 0:
            order.status = OrderStatus.REJECTED
            order.__post_init__()
            self.orders[order.order_id] = order
            return order

        # Determine slippage
        slippage = self.config.base_slippage_bps
        if order.type == OrderType.MARKET:
            slippage = self.config.base_slippage_bps * Decimal("2")  # Market orders pay more

        # Calculate fill price with slippage and market impact
        fill_price = self._apply_slippage(mark_price, order.side, slippage, order.quantity, symbol)

        # Calculate fees (taker fee for market orders, maker for limit)
        is_maker = order.type == OrderType.LIMIT
        fee_bps = self.config.maker_fee_bps if is_maker else self.config.taker_fee_bps
        fees = (order.quantity * fill_price * fee_bps / Decimal("10000")).quantize(Decimal("0.0001"))

        # For limit orders, add to book and wait for match
        if order.type == OrderType.LIMIT and order.price:
            success, queue_pos = self.book_sim.place_order(symbol, order.side, order.price, order.quantity, order.order_id)
            if not success:
                order.status = OrderStatus.REJECTED
                order.__post_init__()
                self.orders[order.order_id] = order
                return order

            # Store queue info for partial fill simulation
            self._order_queue_info[order.order_id] = {
                "queue_position": queue_pos,
                "side": order.side,
                "price": order.price,
                "symbol": symbol,
                "quantity": order.quantity,
                "timestamp": time.time()
            }

            # Simulate partial fill based on queue position
            # In reality, this would be async - here we simulate based on probability
            fill_probability = self._calculate_fill_probability(order, symbol)
            if random.random() < fill_probability:
                fill_qty = min(order.quantity, self._calculate_partial_fill_qty(queue_pos))

                order.filled_quantity = fill_qty
                order.avg_fill_price = fill_price
                order.commission = fees
                order.status = OrderStatus.FILLED if fill_qty == order.quantity else OrderStatus.PARTIALLY_FILLED
            else:
                order.status = OrderStatus.NEW
        else:
            # Market order - match against book
            fills = self.book_sim.match_market_order(symbol, order.side, order.quantity)

            if not fills:
                order.status = OrderStatus.REJECTED
                order.__post_init__()
                self.orders[order.order_id] = order
                return order

            # Calculate VWAP fill price
            total_qty = sum(qty for _, qty, _ in fills)
            total_cost = sum(price * qty for price, qty, _ in fills)
            fill_price = total_cost / total_qty if total_qty > 0 else mark_price

            order.filled_quantity = total_qty
            order.avg_fill_price = fill_price
            order.commission = fees
            order.status = OrderStatus.FILLED if total_qty == order.quantity else OrderStatus.PARTIALLY_FILLED

        order.__post_init__()
        self.orders[order.order_id] = order

        # Update position
        pos = self._position_qty.get(symbol, Decimal("0"))
        if order.side == OrderSide.BUY:
            self._position_qty[symbol] = pos + order.filled_quantity
        else:
            self._position_qty[symbol] = pos - order.filled_quantity

        self._record_round_trip("realistic", symbol, order.type.value, start)
        return order

    def _calculate_fill_probability(self, order: OrderEvent, symbol: str) -> float:
        """Calculate probability of limit order fill based on queue position and market conditions."""
        if not self.config.queue_model.enabled:
            return 0.5

        info = self._order_queue_info.get(order.order_id, {})
        queue_pos = info.get("queue_position", Decimal("0"))
        max_pos = self.config.queue_model.max_queue_position

        # Base probability decreases with queue position
        base_prob = max(0.1, 1.0 - float(queue_pos / max(max_pos, 1)))

        # Adjust for spread tightness
        spread = self.book_sim.get_spread(symbol)
        mid = self.book_sim.get_mid_price(symbol)
        spread_bps = (spread / mid * Decimal("10000")) if mid > 0 else Decimal("100")

        # Tighter spread = higher fill probability
        spread_factor = min(1.0, float(Decimal("50") / max(spread_bps, Decimal("1"))))

        # Adjust for volatility
        vol = self.book_sim.volatilities.get(symbol, Decimal("0.01"))
        vol_factor = min(1.0, float(Decimal("0.01") / max(vol, Decimal("0.001"))))

        return base_prob * spread_factor * vol_factor

    def _calculate_partial_fill_qty(self, queue_position: Decimal) -> Decimal:
        """Calculate partial fill quantity based on queue position."""
        if not self.config.queue_model.enabled:
            return Decimal("1")

        # More likely to get partial fill if deep in queue
        max_pos = self.config.queue_model.max_queue_position
        fill_ratio = max(self.config.queue_model.min_fill_ratio, 1.0 - float(queue_position / max(max_pos, 1)))

        return Decimal(str(fill_ratio))

    async def cancel_order(self, order_id: str) -> bool:
        order = self.orders.get(order_id)
        if not order:
            return False

        # Remove from book if limit order
        if order.type == OrderType.LIMIT and order.price:
            self.book_sim.cancel_order(order.symbol, order.side, order.price, order_id)
            self._order_queue_info.pop(order_id, None)

        order.status = OrderStatus.CANCELED
        order.__post_init__()
        return True

    async def get_price(self, symbol: str) -> Decimal:
        return self.book_sim.get_mid_price(symbol)

    def update_price(self, symbol: str, mid_price: Decimal, volatility: Decimal | None = None) -> None:
        """Update mid price (called from market data feed)."""
        self.book_sim.update_mid_price(symbol, mid_price, volatility)
        self.config.initial_prices[symbol] = mid_price

    @staticmethod
    def _record_round_trip(venue: str, symbol: str, order_type: str, start: float) -> None:
        latency_ms = (time.perf_counter() - start) * 1000.0
        try:
            from cryptobot.monitoring.metrics import record_execution_latency
            record_execution_latency(venue=venue, symbol=symbol, order_type=order_type, latency=latency_ms / 1000.0)
        except Exception as exc:
            logger.debug("metrics record skipped: %s", exc)

    def get_book_snapshot(self, symbol: str, levels: int = 10) -> dict | None:
        """Get order book snapshot for monitoring."""
        if symbol not in self.book_sim.books:
            return None

        book = self.book_sim.books[symbol]
        bids = []
        asks = []

        bid_prices = sorted(book.get(OrderBookSide.BID, {}).keys(), reverse=True)[:levels]
        for price in bid_prices:
            level = book[OrderBookSide.BID][price]
            bids.append({"price": float(price), "quantity": float(level.total_quantity), "orders": len(level.orders)})

        ask_prices = sorted(book.get(OrderBookSide.ASK, {}).keys())[:levels]
        for price in ask_prices:
            level = book[OrderBookSide.ASK][price]
            asks.append({"price": float(price), "quantity": float(level.total_quantity), "orders": len(level.orders)})

        return {
            "symbol": symbol,
            "bids": bids,
            "asks": asks,
            "mid": float(self.book_sim.mid_prices.get(symbol, 0)),
            "spread": float(self.book_sim.get_spread(symbol)),
            "timestamp": time.time()
        }


__all__ = [
    "RealisticVenue",
    "RealisticVenueConfig",
    "LatencyConfig",
    "AdverseSelectionConfig",
    "QueueModelConfig",
    "OrderBookSimulator",
    "PriceLevel",
    "QueuePosition",
    "OrderBookSide",
]
