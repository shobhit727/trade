from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)

from cryptobot.core.clock import ClockFactory, SimulatedClock
from cryptobot.core.events import Event, EventType, OrderEvent, PositionSide
from cryptobot.core.portfolio import PortfolioMode, get_portfolio_manager
from cryptobot.core.state import Position


@dataclass
class BacktestResult:
    """Result of a backtest run."""
    start_time: datetime
    end_time: datetime
    initial_capital: Decimal
    final_equity: Decimal
    total_return: Decimal
    max_drawdown: Decimal
    Sharpe_ratio: Decimal
    Sortino_ratio: Decimal
    win_rate: Decimal
    profit_factor: Decimal
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win: Decimal
    avg_loss: Decimal
    equity_curve: list[tuple[datetime, Decimal]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "initial_capital": str(self.initial_capital),
            "final_equity": str(self.final_equity),
            "total_return": str(self.total_return),
            "max_drawdown": str(self.max_drawdown),
            "Sharpe_ratio": str(self.Sharpe_ratio),
            "Sortino_ratio": str(self.Sortino_ratio),
            "win_rate": str(self.win_rate),
            "profit_factor": str(self.profit_factor),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "avg_win": str(self.avg_win),
            "avg_loss": str(self.avg_loss),
        }


@dataclass
class TradeRecord:
    """Record of a single trade."""
    symbol: str
    entry_time: datetime
    exit_time: datetime
    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    side: str
    pnl: Decimal
    pnl_pct: Decimal
    fees: Decimal
    strategy: str


class BacktestEngine:
    """
    Event-driven backtesting engine.
    
    Manages time progression, event dispatch, and strategy execution.
    """

    def __init__(
        self,
        start_time: datetime,
        end_time: datetime,
        initial_capital: float,
        commission_bps: int = 5,
        slippage_bps: int = 3,
        funding_included: bool = True,
    ):
        self.start_time = start_time
        self.end_time = end_time
        self.initial_capital = Decimal(str(initial_capital))
        self.commission_bps = Decimal(str(commission_bps))
        self.slippage_bps = Decimal(str(slippage_bps))
        self.funding_included = funding_included

        self._clock: SimulatedClock | None = None
        self._portfolio = get_portfolio_manager(PortfolioMode.BACKTEST)
        self._positions: dict[str, Position] = {}
        self._orders: dict[str, OrderEvent] = {}
        self._trades: list[TradeRecord] = []
        self._events: list[Event] = []
        self._initialized = False

    async def initialize(self):
        """Initialize the backtest engine."""
        if self._initialized:
            return

        # Initialize clock
        self._clock = ClockFactory.create_for_backtest(
            start_time=self.start_time,
            end_time=self.end_time,
        )

        # Initialize portfolio
        await self._portfolio.initialize()

        # Set initial equity
        await self._portfolio.update_equity(self.initial_capital)

        self._initialized = True

    async def run(self, data_stream: AsyncIterator[Event]) -> BacktestResult:
        """Run the backtest simulation."""
        await self.initialize()

        logger.info("Starting: %s to %s", self.start_time, self.end_time)
        logger.info("Initial capital: %s", self.initial_capital)

        # Process events
        async for event in data_stream:
            await self._process_event(event)

        # Calculate final results
        final_equity = self._portfolio.get_state().total_equity
        initial = self.initial_capital
        total_return = (final_equity - initial) / initial * Decimal("100")

        # Get max drawdown
        max_dd = self._portfolio.get_state().max_drawdown

        # Calculate Sharpe ratio
        equity_curve = self._portfolio.get_equity_curve()
        returns = []
        for i in range(1, len(equity_curve)):
            prev = equity_curve[i - 1][1]
            curr = equity_curve[i][1]
            if prev > 0:
                returns.append(float((curr - prev) / prev))

        if returns:
            mean_ret = sum(returns) / len(returns)
            std_ret = (sum((r - mean_ret) ** 2 for r in returns) / len(returns)) ** 0.5
            sharpe = Decimal(str(mean_ret / std_ret * (252 ** 0.5))) if std_ret > 0 else Decimal("0")
        else:
            sharpe = Decimal("0")

        # Calculate win rate and profit factor
        winning_trades = [t for t in self._trades if t.pnl > 0]
        losing_trades = [t for t in self._trades if t.pnl < 0]

        if self._trades:
            win_rate = Decimal(str(len(winning_trades) / len(self._trades) * 100))
            if winning_trades:
                avg_win = sum(t.pnl for t in winning_trades) / len(winning_trades)
            else:
                avg_win = Decimal("0")
            if losing_trades:
                avg_loss = sum(t.pnl for t in losing_trades) / len(losing_trades)
                gross_profit = sum(t.pnl for t in winning_trades)
                gross_loss = abs(sum(t.pnl for t in losing_trades))
                profit_factor = gross_profit / gross_loss if gross_loss != 0 else Decimal("0")
            else:
                avg_loss = Decimal("0")
                profit_factor = Decimal("0")
        else:
            win_rate = Decimal("0")
            avg_win = Decimal("0")
            avg_loss = Decimal("0")
            profit_factor = Decimal("0")

        logger.info(
            "Results: final_equity=%s total_return=%s max_dd=%s sharpe=%s trades=%s",
            final_equity, total_return, max_dd, sharpe, len(self._trades),
        )

        return BacktestResult(
            start_time=self.start_time,
            end_time=self.end_time,
            initial_capital=self.initial_capital,
            final_equity=final_equity,
            total_return=total_return,
            max_drawdown=max_dd,
            Sharpe_ratio=sharpe,
            Sortino_ratio=Decimal("0"),
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=len(self._trades),
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            avg_win=avg_win,
            avg_loss=avg_loss,
            equity_curve=equity_curve,
        )

    async def _process_event(self, event: Event):
        """Process a single event."""
        # Update clock time
        if self._clock:
            if event.timestamp > self._clock.current_time:
                delta = event.timestamp - self._clock.current_time
                await self._clock.step(delta)

        # Route event based on type
        if event.type == EventType.TICKER or event.type == EventType.KLINE:
            await self._handle_market_data(event)
        elif event.type == EventType.ORDER_FILLED:
            await self._handle_order_fill(event)
        elif event.type == EventType.POSITION_UPDATE:
            await self._handle_position_update(event)
        elif event.type == EventType.PNL_UPDATE:
            await self._handle_pnl_update(event)

    async def _handle_market_data(self, event: Event):
        """Handle market data events."""
        # Update positions with current prices
        symbol = event.payload.get("symbol", "")
        if symbol and symbol in self._positions:
            pos = self._positions[symbol]

            # Update mark price
            current_price = Decimal(str(event.payload.get("price") or event.payload.get("close_price") or "0"))
            if current_price <= 0:
                # Skip update if no valid price - keep previous mark price
                pass
            else:
                pos.mark_price = current_price

            # Recalculate unrealized PnL
            if pos.side == PositionSide.LONG:
                pos.unrealized_pnl = (current_price - pos.entry_price) * pos.quantity
            else:
                pos.unrealized_pnl = (pos.entry_price - current_price) * pos.quantity

    async def _handle_order_fill(self, event: Event):
        """Handle order fill events."""
        symbol = event.payload.get("symbol", "")
        filled_qty = Decimal(str(event.payload.get("filled_quantity", 0)))
        avg_price = Decimal(str(event.payload.get("avg_fill_price", 0)))
        side = event.payload.get("side", "")

        # Calculate fees
        fees = filled_qty * avg_price * self.commission_bps / Decimal("10000")

        # Get position
        pos = self._positions.get(symbol)

        if pos is None:
            # Open new position
            pos = Position(
                symbol=symbol,
                side=PositionSide.LONG if side == "BUY" else PositionSide.SHORT,
                quantity=filled_qty,
                entry_price=avg_price,
                mark_price=avg_price,
                strategy=event.payload.get("strategy", "backtest"),
            )
            self._positions[symbol] = pos
        else:
            # Update existing position
            if pos.side == (PositionSide.LONG if side == "BUY" else PositionSide.SHORT):
                # Increase position
                total_cost = pos.entry_price * pos.quantity + avg_price * filled_qty
                pos.quantity += filled_qty
                pos.entry_price = total_cost / pos.quantity
            else:
                # Close position
                pnl = Decimal("0")
                if pos.side == PositionSide.LONG:
                    pnl = (avg_price - pos.entry_price) * filled_qty
                else:
                    pnl = (pos.entry_price - avg_price) * filled_qty

                # Record trade
                pnl_net_fees = pnl - fees
                trade = TradeRecord(
                    symbol=symbol,
                    entry_time=pos.opened_at or self._clock.current_time,
                    exit_time=self._clock.current_time,
                    entry_price=pos.entry_price,
                    exit_price=avg_price,
                    quantity=filled_qty,
                    side="long" if pos.side == PositionSide.LONG else "short",
                    pnl=pnl_net_fees,
                    pnl_pct=(pnl_net_fees / (pos.entry_price * filled_qty) * Decimal("100")) if filled_qty > 0 and pos.entry_price > 0 else Decimal("0"),
                    fees=fees,
                    strategy=pos.strategy,
                )
                self._trades.append(trade)

                pos.quantity -= filled_qty
                if pos.quantity <= 0:
                    del self._positions[symbol]

        # Update account state - portfolio tracks equity via positions
        # No need to manually add unrealized_pnl as portfolio.update_equity is called
        # with the correct total equity from position updates
        pass

    async def _handle_position_update(self, event: Event):
        """Handle position update events."""
        symbol = event.payload.get("symbol", "")
        if symbol:
            pos = self._positions.get(symbol)
            if pos:
                await self._portfolio.on_position_update(event)

    async def _handle_pnl_update(self, event: Event):
        """Handle PnL update events."""
        await self._portfolio.on_pnl_update(event)

    def get_trades(self) -> list[TradeRecord]:
        """Get all trade records."""
        return self._trades

    def get_positions(self) -> dict[str, Position]:
        """Get current positions."""
        return self._positions


async def create_backtest_engine(
    start_time: datetime,
    end_time: datetime,
    initial_capital: float = 10000,
) -> BacktestEngine:
    """Create and initialize a backtest engine."""
    engine = BacktestEngine(
        start_time=start_time,
        end_time=end_time,
        initial_capital=initial_capital,
    )
    await engine.initialize()
    return engine
