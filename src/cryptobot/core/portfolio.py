from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple
from uuid import uuid4

from cryptobot.core.events import (
    Event, EventType, OrderEvent, PositionEvent, PnLEvent,
    OrderSide, OrderStatus, PositionSide, OrderType, TimeInForce,
    SignalEvent, SignalSide, SignalStrength
)
from cryptobot.core.state import state_manager, Order, Position, AccountState
from cryptobot.config import settings


class PortfolioMode(str, Enum):
    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"


@dataclass
class StrategyAllocation:
    """Capital allocation for a strategy."""
    strategy: str
    target_weight: Decimal = Decimal("0")
    max_weight: Decimal = Decimal("0.2")
    current_weight: Decimal = Decimal("0")
    capital_allocated: Decimal = Decimal("0")
    capital_used: Decimal = Decimal("0")
    enabled: bool = True
    risk_budget: Decimal = Decimal("0.02")


@dataclass
class PositionMetrics:
    """Metrics for a single position."""
    symbol: str
    side: PositionSide
    quantity: Decimal
    entry_price: Decimal
    mark_price: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    leverage: int
    margin_type: str
    strategy: str
    pnl_pct: Decimal = Decimal("0")

    def __post_init__(self):
        if self.entry_price > 0:
            self.pnl_pct = (
                (self.mark_price - self.entry_price) / self.entry_price * Decimal("100")
                if self.side == PositionSide.LONG
                else (self.entry_price - self.mark_price) / self.entry_price * Decimal("100")
            )


@dataclass
class PortfolioState:
    """Complete portfolio state snapshot."""
    total_equity: Decimal = Decimal("0")
    available_balance: Decimal = Decimal("0")
    used_margin: Decimal = Decimal("0")
    total_unrealized_pnl: Decimal = Decimal("0")
    total_realized_pnl: Decimal = Decimal("0")
    daily_pnl: Decimal = Decimal("0")
    peak_equity: Decimal = Decimal("0")
    max_drawdown: Decimal = Decimal("0")
    open_positions: int = 0
    open_orders: int = 0
    strategies_active: int = 0
    total_return: Decimal = Decimal("0")
    annualized_return: Decimal = Decimal("0")
    volatility: Decimal = Decimal("0")
    Sharpe_ratio: Decimal = Decimal("0")
    Sortino_ratio: Decimal = Decimal("0")
    max_drawdown_pct: Decimal = Decimal("0")
    win_rate: Decimal = Decimal("0")
    profit_factor: Decimal = Decimal("0")
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "total_equity": str(self.total_equity),
            "available_balance": str(self.available_balance),
            "used_margin": str(self.used_margin),
            "total_unrealized_pnl": str(self.total_unrealized_pnl),
            "total_realized_pnl": str(self.total_realized_pnl),
            "daily_pnl": str(self.daily_pnl),
            "peak_equity": str(self.peak_equity),
            "max_drawdown": str(self.max_drawdown),
            "open_positions": self.open_positions,
            "open_orders": self.open_orders,
            "strategies_active": self.strategies_active,
            "total_return": str(self.total_return),
            "annualized_return": str(self.annualized_return),
            "volatility": str(self.volatility),
            "Sharpe_ratio": str(self.Sharpe_ratio),
            "Sortino_ratio": str(self.Sortino_ratio),
            "max_drawdown_pct": str(self.max_drawdown_pct),
            "win_rate": str(self.win_rate),
            "profit_factor": str(self.profit_factor),
            "updated_at": self.updated_at.isoformat(),
        }


class PortfolioManager:
    """Multi-strategy portfolio management."""

    def __init__(self, mode: PortfolioMode = PortfolioMode.PAPER):
        self.mode = mode
        self._allocations: Dict[str, StrategyAllocation] = {}
        self._state = PortfolioState()
        self._daily_pnl_start: Decimal = Decimal("0")
        self._equity_curve: List[Tuple[datetime, Decimal]] = []
        self._lock = asyncio.Lock()
        self._initialized = False
        self._daily_returns: List[Decimal] = []

    async def initialize(self):
        """Initialize from persistent state."""
        async with self._lock:
            if self._initialized:
                return

            account = state_manager.get_account()
            self._state.total_equity = account.total_equity
            self._state.available_balance = account.available_balance
            self._state.used_margin = account.used_margin
            self._state.total_unrealized_pnl = account.total_unrealized_pnl
            self._state.total_realized_pnl = account.total_realized_pnl
            self._state.daily_pnl = account.daily_pnl
            self._state.peak_equity = account.peak_equity
            self._state.max_drawdown = account.max_drawdown
            self._daily_pnl_start = account.total_equity - account.daily_pnl
            self._equity_curve.append((datetime.utcnow(), account.total_equity))

            positions = state_manager.get_positions()
            self._state.open_positions = len([p for p in positions if p.quantity > 0])

            orders = state_manager.get_open_orders()
            self._state.open_orders = len(orders)

            self._initialized = True

    def register_strategy(
        self,
        strategy: str,
        target_weight: Decimal,
        max_weight: Optional[Decimal] = None,
        risk_budget: Optional[Decimal] = None,
    ):
        """Register a strategy with capital allocation."""
        if strategy in self._allocations:
            return

        self._allocations[strategy] = StrategyAllocation(
            strategy=strategy,
            target_weight=target_weight,
            max_weight=max_weight or Decimal(str(settings.risk.max_single_position_pct)),
            risk_budget=risk_budget or Decimal(str(settings.risk.max_daily_loss_pct)) / Decimal("10"),
        )

    def get_allocation(self, strategy: str) -> Optional[StrategyAllocation]:
        return self._allocations.get(strategy)

    def get_all_allocations(self) -> List[StrategyAllocation]:
        return list(self._allocations.values())

    async def update_equity(self, equity: Decimal):
        """Update portfolio equity and recalculate metrics."""
        async with self._lock:
            if self._state.total_equity > 0:
                daily_return = (equity - self._state.total_equity) / self._state.total_equity
                self._daily_returns.append(daily_return)

            self._state.total_equity = equity
            self._equity_curve.append((datetime.utcnow(), equity))

            if equity > self._state.peak_equity:
                self._state.peak_equity = equity

            if self._state.peak_equity > 0:
                drawdown = (self._state.peak_equity - equity) / self._state.peak_equity
                if drawdown > self._state.max_drawdown:
                    self._state.max_drawdown = drawdown

            self._state.daily_pnl = equity - self._daily_pnl_start

            state_manager.update_account_equity(equity)

    async def on_position_update(self, event: PositionEvent):
        """Handle position update event."""
        async with self._lock:
            positions = state_manager.get_positions()
            self._state.open_positions = len([p for p in positions if p.quantity > 0])

            for alloc in self._allocations.values():
                strat_positions = [
                    p for p in positions
                    if p.strategy == alloc.strategy and p.quantity > 0
                ]
                alloc.capital_used = sum(
                    p.quantity * p.mark_price for p in strat_positions
                )
                if self._state.total_equity > 0:
                    alloc.current_weight = alloc.capital_used / self._state.total_equity

    async def on_order_update(self, event: OrderEvent):
        """Handle order update event."""
        async with self._lock:
            orders = state_manager.get_open_orders()
            self._state.open_orders = len(orders)

    async def on_pnl_update(self, event: PnLEvent):
        """Handle PnL update event."""
        async with self._lock:
            self._state.total_unrealized_pnl = Decimal(str(event.payload.get("total_unrealized", "0")))
            self._state.total_realized_pnl = Decimal(str(event.payload.get("total_realized", "0")))
            self._state.available_balance = Decimal(str(event.payload.get("available_balance", "0")))
            self._state.used_margin = Decimal(str(event.payload.get("used_margin", "0")))

    def get_state(self) -> PortfolioState:
        """Get current portfolio state."""
        return self._state

    def get_equity_curve(self) -> List[Tuple[datetime, Decimal]]:
        return self._equity_curve.copy()

    def get_daily_pnl_pct(self) -> float:
        if self._daily_pnl_start > 0:
            return float(self._state.daily_pnl / self._daily_pnl_start)
        return 0.0

    def get_drawdown_pct(self) -> float:
        return float(self._state.max_drawdown)

    def check_kill_switch(self) -> Tuple[bool, str]:
        """Check if kill switch should trigger."""
        daily_loss_pct = self.get_daily_pnl_pct()
        max_allowed = float(settings.risk.kill_switch_daily_loss_pct)

        if daily_loss_pct <= -max_allowed:
            return True, f"Daily loss {daily_loss_pct:.2%} exceeds kill switch {max_allowed:.2%}"

        drawdown_pct = self.get_drawdown_pct()
        max_dd = float(settings.risk.max_drawdown_pct)

        if drawdown_pct >= max_dd:
            return True, f"Max drawdown {drawdown_pct:.2%} exceeds limit {max_dd:.2%}"

        return False, ""

    def reset_daily_pnl(self):
        """Reset daily PnL tracking."""
        self._daily_pnl_start = self._state.total_equity
        self._state.daily_pnl = Decimal("0")
        state_manager.reset_daily_pnl()

    def calculate_available_capital(self, strategy: str) -> Decimal:
        """Calculate available capital for a strategy."""
        alloc = self._allocations.get(strategy)
        if not alloc or not alloc.enabled:
            return Decimal("0")

        max_capital = self._state.total_equity * alloc.max_weight
        available = max_capital - alloc.capital_used

        daily_loss_limit = self._state.total_equity * alloc.risk_budget
        if self._state.daily_pnl < -daily_loss_limit:
            return Decimal("0")

        return max(available, Decimal("0"))

    def get_strategy_metrics(self, strategy: str) -> dict:
        """Get performance metrics for a strategy."""
        alloc = self._allocations.get(strategy)
        if not alloc:
            return {}

        positions = state_manager.get_positions(strategy=strategy)
        orders = state_manager.get_orders(strategy=strategy)

        realized = sum(p.realized_pnl for p in positions)
        unrealized = sum(p.unrealized_pnl for p in positions)

        return {
            "strategy": strategy,
            "allocated": str(alloc.capital_allocated),
            "used": str(alloc.capital_used),
            "target_weight": str(alloc.target_weight),
            "current_weight": str(alloc.current_weight),
            "max_weight": str(alloc.max_weight),
            "realized_pnl": str(realized),
            "unrealized_pnl": str(unrealized),
            "total_pnl": str(realized + unrealized),
            "open_positions": len([p for p in positions if p.quantity > 0]),
            "open_orders": len([o for o in orders if o.status in (OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED)]),
            "enabled": alloc.enabled,
        }

    def get_position_metrics(self) -> List[PositionMetrics]:
        """Get metrics for all positions."""
        positions = state_manager.get_positions()
        metrics = []

        for pos in positions:
            if pos.quantity > 0:
                metric = PositionMetrics(
                    symbol=pos.symbol,
                    side=pos.side,
                    quantity=pos.quantity,
                    entry_price=pos.entry_price,
                    mark_price=pos.mark_price,
                    unrealized_pnl=pos.unrealized_pnl,
                    realized_pnl=pos.realized_pnl,
                    leverage=pos.leverage,
                    margin_type=pos.margin_type,
                    strategy=pos.strategy,
                )
                metrics.append(metric)

        return metrics

    def calculate_portfolio_metrics(self):
        """Calculate comprehensive portfolio metrics."""
        if len(self._equity_curve) < 2:
            return

        returns = []
        for i in range(1, len(self._equity_curve)):
            prev_equity = self._equity_curve[i - 1][1]
            curr_equity = self._equity_curve[i][1]
            if prev_equity > 0:
                ret = (curr_equity - prev_equity) / prev_equity
                returns.append(ret)

        if returns:
            self._state.total_return = (
                self._state.total_equity - self._equity_curve[0][1]
            ) / self._equity_curve[0][1] * Decimal("100")

            daily_returns_array = [float(r) for r in returns]
            mean_return = sum(daily_returns_array) / len(daily_returns_array)

            volatility = (
                sum((r - mean_return) ** 2 for r in daily_returns_array)
                / len(daily_returns_array)
            ) ** 0.5

            self._state.volatility = Decimal(str(volatility * (252 ** 0.5)))

            if volatility > 0:
                self._state.Sharpe_ratio = Decimal(str(mean_return / volatility * (252 ** 0.5)))

            wins = [r for r in returns if r > 0]
            losses = [r for r in returns if r < 0]

            if losses:
                win_rate = len(wins) / len(returns)
                self._state.win_rate = Decimal(str(win_rate * 100))

                total_wins = sum(float(r) for r in wins)
                total_losses = abs(sum(float(r) for r in losses))

                if total_losses > 0:
                    self._state.profit_factor = Decimal(str(total_wins / total_losses))

            positive_returns = [r for r in daily_returns_array if r > 0]
            negative_returns = [r for r in daily_returns_array if r < 0]

            if negative_returns:
                downside_vol = (
                    sum(r ** 2 for r in negative_returns) / len(negative_returns)
                ) ** 0.5

                if downside_vol > 0:
                    self._state.Sortino_ratio = Decimal(str(mean_return / downside_vol * (252 ** 0.5)))


# Global portfolio manager
_portfolio_manager: Optional[PortfolioManager] = None


def get_portfolio_manager(mode: PortfolioMode = PortfolioMode.PAPER) -> PortfolioManager:
    """Get global portfolio manager."""
    global _portfolio_manager
    if _portfolio_manager is None:
        _portfolio_manager = PortfolioManager(mode)
    return _portfolio_manager


async def init_portfolio_manager(mode: PortfolioMode = PortfolioMode.PAPER) -> PortfolioManager:
    """Initialize global portfolio manager."""
    global _portfolio_manager
    _portfolio_manager = PortfolioManager(mode)
    await _portfolio_manager.initialize()
    return _portfolio_manager
