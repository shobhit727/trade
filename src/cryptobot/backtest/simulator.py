from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from cryptobot.core.clock import Clock
from cryptobot.core.events import OrderEvent
from cryptobot.utils.types import OrderBook


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class FillParams:
    """Parameters for fill simulation."""
    commission_bps: Decimal = Decimal("5")
    slippage_bps: Decimal = Decimal("3")
    max_slippage_bps: Decimal = Decimal("20")
    funding_rate_included: bool = True
    min_order_size: Decimal = Decimal("10")
    max_order_size: Decimal = Decimal("10000")


@dataclass
class FillResult:
    """Result of a fill simulation."""
    fill_price: Decimal
    fill_quantity: Decimal
    commission: Decimal
    slippage_bps: Decimal
    fill_time: datetime
    is_partial: bool = False
    is_maker: bool = False
    funding_payment: Decimal | None = None


class FillSimulator:
    """
    Realistic fill simulator with slippage, fees, and market impact.

    Models:
    - Slippage based on order size and volatility
    - Market impact for large orders
    - Funding payments for perpetuals
    - Partial fills
    """

    def __init__(self, params: FillParams | None = None):
        self.params = params or FillParams()
        self._volatility: dict[str, Decimal] = {}
        self._order_book: dict[str, OrderBook] = {}

    def update_volatility(self, symbol: str, volatility: float):
        """Update symbol volatility estimate."""
        self._volatility[symbol] = Decimal(str(volatility))

    def update_order_book(self, order_book: OrderBook):
        """Update order book state."""
        self._order_book[order_book.symbol] = order_book

    async def simulate_fill(
        self,
        order_event: OrderEvent,
        current_price: Decimal | None = None,
        clock: Clock | None = None,
    ) -> FillResult | None:
        """Simulate order fill with realistic parameters."""
        symbol = order_event.symbol
        order_side = order_event.side
        order_quantity = order_event.quantity
        order_type = order_event.type

        # Get current price from order book or use mark price
        if current_price is None:
            order_book = self._order_book.get(symbol)
            if order_book and order_book.mid_price:
                current_price = order_book.mid_price
            else:
                # Fallback: use order price
                current_price = order_event.price or Decimal("0")

        if current_price == Decimal("0"):
            return None

        # Calculate fill quantity (could be partial)
        fill_quantity = order_quantity
        fill_probability = self._calculate_fill_probability(
            symbol, order_quantity, current_price
        )

        if random.random() > fill_probability:
            # Partial fill
            fill_quantity = order_quantity * Decimal(str(random.uniform(0.5, 1.0)))
            is_partial = True
        else:
            is_partial = False

        # Calculate slippage based on order size and market conditions
        slippage_bps = self._calculate_slippage(
            symbol, order_side, order_quantity, current_price
        )

        # Calculate fill price with slippage
        if order_side == "BUY":
            fill_price = current_price * (Decimal("1") + slippage_bps / Decimal("10000"))
        else:
            fill_price = current_price * (Decimal("1") - slippage_bps / Decimal("10000"))

        # Round to tick size (assume 0.01 for USDT pairs)
        fill_price = fill_price.quantize(Decimal("0.01"))

        # Calculate commission
        commission = fill_quantity * fill_price * self.params.commission_bps / Decimal("10000")

        # Calculate funding payment if applicable
        funding_payment = None
        if self.params.funding_rate_included and symbol.endswith("USDT"):
            # Simulate funding rate (typically 0.01% - 0.1% per 8 hours)
            funding_rate = Decimal(str(random.uniform(-0.0005, 0.0005)))
            funding_payment = fill_quantity * funding_rate

        # Calculate fill time
        fill_time = clock.current_time if clock else _utcnow()

        return FillResult(
            fill_price=fill_price,
            fill_quantity=fill_quantity,
            commission=commission,
            slippage_bps=slippage_bps,
            fill_time=fill_time,
            is_partial=is_partial,
            is_maker=order_type == "LIMIT",
            funding_payment=funding_payment,
        )

    def _calculate_fill_probability(
        self, symbol: str, quantity: Decimal, price: Decimal
    ) -> float:
        """Calculate probability of full fill based on market depth."""
        order_book = self._order_book.get(symbol)

        if not order_book:
            # Default to 95% fill probability
            return 0.95

        # Calculate order size as percentage of book depth
        if order_book.bids and order_book.asks:
            book_depth = sum(
                level.quantity for level in order_book.bids[:5]
            ) + sum(level.quantity for level in order_book.asks[:5])

            order_size_pct = float(quantity / book_depth) if book_depth > 0 else 1.0

            # Larger orders have lower fill probability
            base_prob = 0.95
            size_penalty = min(order_size_pct * 0.3, 0.3)

            return base_prob - size_penalty

        return 0.95

    def _calculate_slippage(
        self, symbol: str, side: str, quantity: Decimal, price: Decimal
    ) -> Decimal:
        """Calculate slippage based on order characteristics."""
        base_slippage = self.params.slippage_bps

        # Add slippage for larger orders (market impact)
        order_value = quantity * price
        if order_value > Decimal("10000"):
            base_slippage += Decimal("2")
        if order_value > Decimal("50000"):
            base_slippage += Decimal("3")
        if order_value > Decimal("100000"):
            base_slippage += Decimal("5")

        # Add volatility component
        volatility = self._volatility.get(symbol, Decimal("0.02"))
        volatility_slippage = volatility * Decimal("100")
        base_slippage += volatility_slippage

        # Add slippage for larger quantities
        quantity_slippage = min(Decimal(str(quantity / 1000)) * Decimal("0.5"), Decimal("5"))
        base_slippage += quantity_slippage

        # Cap at max slippage
        base_slippage = min(base_slippage, self.params.max_slippage_bps)

        return base_slippage

    def calculate_total_cost(self, fill: FillResult, quantity: Decimal) -> Decimal:
        """Calculate total cost including fees and slippage."""
        total_cost = fill.fill_price * quantity + fill.commission

        if fill.funding_payment:
            total_cost += fill.funding_payment

        return total_cost

    def calculate_realized_pnl(
        self,
        entry_price: Decimal,
        exit_price: Decimal,
        quantity: Decimal,
        side: str,
    ) -> Decimal:
        """Calculate realized PnL for a closed position."""
        if side == "BUY":
            pnl = (exit_price - entry_price) * quantity
        else:
            pnl = (entry_price - exit_price) * quantity

        return pnl


class FillSimulatorFactory:
    """Factory for creating fill simulators."""

    @staticmethod
    def create_for_backtest(
        commission_bps: int = 5,
        slippage_bps: int = 3,
        funding_included: bool = True,
    ) -> FillSimulator:
        """Create simulator for backtesting."""
        params = FillParams(
            commission_bps=Decimal(str(commission_bps)),
            slippage_bps=Decimal(str(slippage_bps)),
            funding_rate_included=funding_included,
        )
        return FillSimulator(params)

    @staticmethod
    def create_for_paper(
        commission_bps: int = 5,
        slippage_bps: int = 3,
        funding_included: bool = True,
    ) -> FillSimulator:
        """Create simulator for paper trading."""
        params = FillParams(
            commission_bps=Decimal(str(commission_bps)),
            slippage_bps=Decimal(str(slippage_bps)),
            funding_rate_included=funding_included,
        )
        return FillSimulator(params)

    @staticmethod
    def create_for_live(
        commission_bps: int = 5,
        max_slippage_bps: int = 20,
        funding_included: bool = True,
    ) -> FillSimulator:
        """Create simulator for live trading with tighter constraints."""
        params = FillParams(
            commission_bps=Decimal(str(commission_bps)),
            slippage_bps=Decimal(str(max_slippage_bps // 2)),
            max_slippage_bps=Decimal(str(max_slippage_bps)),
            funding_rate_included=funding_included,
        )
        return FillSimulator(params)


async def create_fill_simulator(
    mode: str = "backtest",
    commission_bps: int = 5,
    slippage_bps: int = 3,
    funding_included: bool = True,
) -> FillSimulator:
    """Create and configure fill simulator."""
    if mode == "backtest":
        return FillSimulatorFactory.create_for_backtest(
            commission_bps=commission_bps,
            slippage_bps=slippage_bps,
            funding_included=funding_included,
        )
    elif mode == "paper":
        return FillSimulatorFactory.create_for_paper(
            commission_bps=commission_bps,
            slippage_bps=slippage_bps,
            funding_included=funding_included,
        )
    elif mode == "live":
        return FillSimulatorFactory.create_for_live(
            commission_bps=commission_bps,
            max_slippage_bps=20,
            funding_included=funding_included,
        )
    else:
        raise ValueError(f"Unknown mode: {mode}")
