from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from cryptobot.backtest.funding import FundingProvider, funding_cashflow
from cryptobot.core.clock import ClockFactory, SimulatedClock
from cryptobot.core.events import Event, EventType, OrderEvent, OrderStatus, PositionSide
from cryptobot.core.portfolio import PortfolioManager, PortfolioMode
from cryptobot.core.state import Position

logger = logging.getLogger(__name__)


def _periods_per_year(equity_curve: list[tuple[datetime, Decimal]]) -> int:
    """Estimate periods per year from equity curve timestamps."""
    if len(equity_curve) < 2:
        return 252  # default to daily
    intervals = []
    for i in range(1, len(equity_curve)):
        delta = equity_curve[i][0] - equity_curve[i - 1][0]
        intervals.append(delta.total_seconds())
    if not intervals:
        return 252
    avg_interval = sum(intervals) / len(intervals)
    # 1 year = 365.25 days = 31557600 seconds
    periods = 31557600 / max(avg_interval, 1)
    return max(int(round(periods)), 1)


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
        portfolio: PortfolioManager | None = None,
        funding: FundingProvider | None = None,
    ):
        self.start_time = start_time
        self.end_time = end_time
        self.initial_capital = Decimal(str(initial_capital))
        self.commission_bps = Decimal(str(commission_bps))
        self.slippage_bps = Decimal(str(slippage_bps))
        self.funding_included = funding_included
        self.funding = funding

        self._clock: SimulatedClock | None = None
        self._owns_portfolio = portfolio is None
        self._portfolio = portfolio or PortfolioManager(PortfolioMode.BACKTEST)
        self._positions: dict[str, Position] = {}
        self._orders: dict[str, OrderEvent] = {}
        self._trades: list[TradeRecord] = []
        self._events: list[Event] = []
        self._cash: Decimal = Decimal("0")
        self._initialized = False
        self._last_settlement_block: tuple[object, int] | None = None

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
        if not self._owns_portfolio:
            await self._portfolio.initialize()

        # Set initial equity
        self._cash = self.initial_capital
        await self._portfolio.update_equity(self.initial_capital)

        self._initialized = True

    async def run(self, data_stream: AsyncIterator[Event]) -> BacktestResult:
        """Run the backtest simulation from an event stream."""
        await self.initialize()

        logger.info("Starting: %s to %s", self.start_time, self.end_time)
        logger.info("Initial capital: %s", self.initial_capital)

        # Process events
        async for event in data_stream:
            await self._process_event(event)

        return self._compute_result()

    async def run_bars(self, bars, strategy, symbol: str, execution_engine) -> BacktestResult:
        """Run the backtest simulation directly over bars.

        Fast path: the strategy is fed synchronously bar-by-bar and only dips
        into the async machinery (clock stepping, order submission, portfolio
        accounting) when the strategy actually fires an order. This avoids
        allocating a ticker Event and two coroutine hops per bar -- the common
        case for long synthetic backtests.
        """
        await self.initialize()

        logger.info("Starting: %s to %s", self.start_time, self.end_time)
        logger.info("Initial capital: %s", self.initial_capital)

        feed = strategy.feed
        if getattr(strategy, "name", "") == "trend_following":
            for bar in bars:
                await self._maybe_settle_funding(bar.timestamp)
                order = feed(symbol, bar.high, bar.low, bar.close)
                if order is None:
                    continue
                await self._run_orders(order, execution_engine, bar, str(bar.close), strategy)
        else:
            for bar in bars:
                await self._maybe_settle_funding(bar.timestamp)
                order = feed(symbol, bar.close)
                if order is None:
                    continue
                await self._run_orders(order, execution_engine, bar, str(bar.close), strategy)

        return self._compute_result()

    async def _run_orders(
        self,
        order,
        execution_engine,
        bar,
        close_str: str,
        strategy,
    ) -> None:
        """Submit a strategy order at bar close and process the resulting fills."""
        if not isinstance(order, list):
            order = [order]
        for o in order:
            if o is None:
                continue
            if o.reduce_only and o.symbol not in self._positions:
                # Exit signal for a position the engine never opened (e.g. the
                # entry was rejected by risk): do not open a new position.
                continue
            # Keep the venue's mark price current so market orders fill at bar close
            execution_engine.venue.prices[o.symbol] = Decimal(close_str)
            filled = await execution_engine.submit_order(o)
            if filled.status == OrderStatus.FILLED:
                fill_price = str(filled.avg_fill_price) if filled.avg_fill_price else close_str
                # Refresh mark-to-market for open positions at this bar's close
                # (mirrors what the per-bar ticker used to do) and record the fill.
                await self._process_event(
                    Event(
                        type=EventType.TICKER,
                        timestamp=bar.timestamp,
                        payload={
                            "symbol": filled.symbol,
                            "price": fill_price,
                            "close_price": fill_price,
                        },
                    )
                )
                await self._process_event(
                    Event(
                        type=EventType.ORDER_FILLED,
                        timestamp=bar.timestamp,
                        payload={
                            "symbol": filled.symbol,
                            "filled_quantity": str(filled.filled_quantity),
                            "avg_fill_price": str(filled.avg_fill_price or Decimal("0")),
                            "side": filled.side.value,
                            "strategy": filled.strategy or strategy.name,
                            "unrealized_pnl": "0",
                            "fees": str(filled.commission),
                        },
                    )
                )

    async def _maybe_settle_funding(self, ts: datetime) -> None:
        """Apply 8h perp funding to open positions (at most once per 8h block).

        Called before every bar; the 8h block is keyed by (day, hour/8) so
        duplicate bar timestamps within the same block settle once.
        """
        if not self.funding_included or self.funding is None or not self._positions:
            return
        if not FundingProvider.is_settlement(ts):
            return
        utc_ts = ts.astimezone(UTC) if ts.tzinfo else ts.replace(tzinfo=UTC)
        block = (utc_ts.date(), utc_ts.hour // 8)
        if self._last_settlement_block == block:
            return
        for pos in self._positions.values():
            rate = self.funding.rate(pos.symbol, ts)
            self._cash += funding_cashflow(pos.side.value, pos.quantity, pos.mark_price, rate)
        self._last_settlement_block = block
        await self._update_equity()

    def _compute_result(self) -> BacktestResult:
        """Finalize and report statistics from the recorded trades/equity."""
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
            std_ret = (sum((r - mean_ret) ** 2 for r in returns) / max(len(returns) - 1, 1)) ** 0.5
            periods = _periods_per_year(equity_curve)
            sharpe = Decimal(str(mean_ret / std_ret * (periods ** 0.5))) if std_ret > 0 else Decimal("0")

            # Calculate Sortino ratio
            negative_returns = [r for r in returns if r < 0]
            if negative_returns:
                downside_vol = (sum(r ** 2 for r in negative_returns) / max(len(negative_returns) - 1, 1)) ** 0.5
                sortino = Decimal(str(mean_ret / downside_vol * (periods ** 0.5))) if downside_vol > 0 else Decimal("0")
            else:
                sortino = Decimal("0")
        else:
            sharpe = Decimal("0")
            sortino = Decimal("0")

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
            Sortino_ratio=sortino,
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
            await self._maybe_settle_funding(event.timestamp)
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
                opened_at=self._clock.current_time,
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
                # Opposite side: close (or over-close, flipping side)
                close_qty = min(pos.quantity, filled_qty)
                pnl = Decimal("0")
                if pos.side == PositionSide.LONG:
                    pnl = (avg_price - pos.entry_price) * close_qty
                else:
                    pnl = (pos.entry_price - avg_price) * close_qty

                # Record trade
                pnl_net_fees = pnl - fees
                trade = TradeRecord(
                    symbol=symbol,
                    entry_time=pos.opened_at or self._clock.current_time,
                    exit_time=self._clock.current_time,
                    entry_price=pos.entry_price,
                    exit_price=avg_price,
                    quantity=close_qty,
                    side="long" if pos.side == PositionSide.LONG else "short",
                    pnl=pnl_net_fees,
                    pnl_pct=(pnl_net_fees / (pos.entry_price * close_qty) * Decimal("100")) if close_qty > 0 and pos.entry_price > 0 else Decimal("0"),
                    fees=fees,
                    strategy=pos.strategy,
                )
                self._trades.append(trade)

                pos.quantity -= filled_qty
                if pos.quantity < 0:
                    # Over-close: flip to the opposite side with the remainder
                    pos.side = PositionSide.LONG if side == "BUY" else PositionSide.SHORT
                    pos.quantity = -pos.quantity
                    pos.entry_price = avg_price
                    pos.mark_price = avg_price
                    pos.opened_at = self._clock.current_time
                elif pos.quantity == 0:
                    del self._positions[symbol]

        # Cash accounting: buys spend cash, sells receive cash (net of fees)
        if side == "BUY":
            self._cash -= avg_price * filled_qty + fees
        else:
            self._cash += avg_price * filled_qty - fees

        # Update portfolio equity (cash + mark-to-market positions)
        await self._update_equity()

    async def _update_equity(self):
        """Recompute equity as cash plus mark-to-market position value."""
        equity = self._cash
        for pos in self._positions.values():
            if pos.side == PositionSide.LONG:
                equity += pos.quantity * pos.mark_price
            else:
                equity -= pos.quantity * pos.mark_price
        await self._portfolio.update_equity(equity)

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
