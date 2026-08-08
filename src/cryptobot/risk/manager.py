from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal
from time import time

from cryptobot.config import settings
from cryptobot.core.events import OrderEvent, RiskEvent
from cryptobot.core.portfolio import PortfolioManager, get_portfolio_manager
from cryptobot.core.state import state_manager
from cryptobot.monitoring.metrics import record_risk
from cryptobot.risk.kill_switch import KillSwitch
from cryptobot.risk.limits import RiskLimits
from cryptobot.risk.rate_limit import RateLimiter
from cryptobot.risk.sizing import (
    fixed_fraction_size,
    kelly_size,
    volatility_target_size,
)
from cryptobot.risk.strategy_tracker import StrategyRiskTracker


@dataclass
class RiskCheckResult:
    passed: bool
    message: str = ""
    current_value: Decimal | None = None
    limit_value: Decimal | None = None

    def to_event(self, check_type: str, order: OrderEvent) -> RiskEvent:
        return RiskEvent(
            check_type=check_type,
            passed=self.passed,
            message=self.message,
            current_value=str(self.current_value) if self.current_value is not None else None,
            limit_value=str(self.limit_value) if self.limit_value is not None else None,
            symbol=order.symbol,
            strategy=order.strategy,
        )


@dataclass
class RiskManager:
    portfolio: PortfolioManager = field(default_factory=get_portfolio_manager)
    limits: RiskLimits = field(default_factory=RiskLimits)
    kill_switch: KillSwitch = field(default_factory=KillSwitch)
    rate_limiter: RateLimiter = field(init=False)
    strategy_tracker: StrategyRiskTracker = field(default_factory=StrategyRiskTracker)
    _price_history: dict[str, deque[tuple[float, Decimal]]] = field(default_factory=dict)
    _order_count: int = 0
    # When True (backtest path), wall-clock based checks (order rate limiting,
    # reference-price history) are skipped — they would otherwise make results
    # depend on real elapsed time instead of simulated time.
    backtest_mode: bool = False

    def __post_init__(self):
        self.rate_limiter = RateLimiter(
            max_events=self.limits.max_orders_per_minute,
            window_seconds=60.0,
        )

    def compute_position_size(
        self,
        equity: Decimal,
        price: Decimal,
        win_rate: Decimal = Decimal("0.55"),
        win_loss_ratio: Decimal = Decimal("1.5"),
        observed_vol: Decimal | None = None,
    ) -> Decimal:
        method = settings.risk.position_sizing
        scaling = self._drawdown_scale()
        equity = equity * scaling
        if method == "fixed":
            return fixed_fraction_size(
                equity,
                Decimal(str(settings.risk.max_single_position_pct)),
                price,
            )
        if method == "volatility_target":
            return volatility_target_size(
                equity,
                Decimal(str(settings.risk.volatility_target)),
                observed_vol or Decimal("0"),
                price,
            )
        return kelly_size(equity, win_rate, win_loss_ratio, price)

    def check_order(
        self,
        order: OrderEvent,
        price: Decimal | None = None,
        correlation_matrix: dict[tuple[str, str], Decimal] | None = None,
    ) -> RiskCheckResult:
        self._order_count += 1
        self.report_risk_metrics()

        active, reason = self.kill_switch.evaluate(self.portfolio)
        if active and not self.backtest_mode:
            return RiskCheckResult(False, f"Kill switch active: {reason}")

        if not self.rate_limiter.try_acquire() and not self.backtest_mode:
            return RiskCheckResult(
                False,
                f"Order rate exceeded ({self.limits.max_orders_per_minute}/min)",
            )

        notional_price = price or order.price or order.avg_fill_price
        if notional_price is not None and notional_price > 0:
            notional = order.quantity * notional_price
        else:
            notional = Decimal("0")

        if not self.backtest_mode and notional > 0:
            if notional < self.limits.min_order_size_usd:
                return RiskCheckResult(
                    False,
                    "Order below minimum size",
                    notional,
                    self.limits.min_order_size_usd,
                )
            if notional > self.limits.max_order_size_usd:
                return RiskCheckResult(
                    False,
                    "Order above maximum size",
                    notional,
                    self.limits.max_order_size_usd,
                )

            if order.leverage > 0 and order.leverage > self.limits.max_leverage:
                return RiskCheckResult(
                    False,
                    f"Leverage {order.leverage}x exceeds limit {self.limits.max_leverage}x",
                    Decimal(str(order.leverage)),
                    self.limits.max_leverage,
                )

            ref_price = self._get_reference_price(order.symbol)
            if ref_price is not None and ref_price > 0:
                deviation = abs(notional_price - ref_price) / ref_price
                if deviation > self.limits.price_deviation_pct:
                    return RiskCheckResult(
                        False,
                        f"Price deviates {deviation:.2%} from reference (> {self.limits.price_deviation_pct:.2%})",
                        deviation,
                        self.limits.price_deviation_pct,
                    )
            self._record_price(order.symbol, notional_price)

        state = self.portfolio.get_state()
        if state.total_equity > 0 and not self.backtest_mode:
            open_positions = sum(1 for p in state_manager.get_positions() if p.quantity > 0)
            if open_positions >= self.limits.max_open_positions:
                return RiskCheckResult(
                    False,
                    f"Max open positions reached ({self.limits.max_open_positions})",
                    Decimal(open_positions),
                    Decimal(self.limits.max_open_positions),
                )

            additional = notional if notional > 0 else Decimal("0")
            total_exposure = (state.used_margin + additional) / state.total_equity
            if total_exposure > self.limits.max_total_exposure_pct:
                return RiskCheckResult(
                    False,
                    "Total exposure limit exceeded",
                    total_exposure,
                    self.limits.max_total_exposure_pct,
                )

            if notional > 0:
                position_pct = notional / state.total_equity
                scaled_cap = self.limits.max_single_position_pct * self._drawdown_scale()
                if position_pct > scaled_cap:
                    return RiskCheckResult(
                        False,
                        f"Position size {position_pct:.2%} exceeds scaled limit {scaled_cap:.2%}",
                        position_pct,
                        scaled_cap,
                    )

        if correlation_matrix and notional > 0:
            for (a, b), corr in correlation_matrix.items():
                if a == order.symbol or b == order.symbol:
                    if abs(corr) > self.limits.max_correlation:
                        return RiskCheckResult(
                            False,
                            f"Correlation with {a}/{b} = {corr:.2f} exceeds limit {self.limits.max_correlation:.2f}",
                            abs(corr),
                            self.limits.max_correlation,
                        )

        if (
            not self.backtest_mode
            and notional >= self.limits.require_stop_loss_above_usd
            and order.stop_price is None
        ):
            return RiskCheckResult(
                False,
                f"Stop-loss required for orders > {self.limits.require_stop_loss_above_usd} USD",
                notional,
                self.limits.require_stop_loss_above_usd,
            )

        strat_state = self.strategy_tracker.get(order.strategy)
        if strat_state.daily_pnl < -self.limits.max_daily_loss_pct * state.total_equity:
            return RiskCheckResult(
                False,
                f"Strategy {order.strategy} daily loss limit exceeded",
                strat_state.daily_pnl,
                -self.limits.max_daily_loss_pct * state.total_equity,
            )

        return RiskCheckResult(True, "OK")

    def report_risk_metrics(self) -> None:
        """Emit current portfolio risk gauges (Prometheus). Safe to call on a timer."""
        state = self.portfolio.get_state()
        equity = state.total_equity
        if equity <= 0:
            return
        exposure = (state.used_margin + Decimal("0")) / equity
        daily_loss = abs(state.daily_pnl) / equity if state.daily_pnl < 0 else Decimal("0")
        active, _reason = self.kill_switch.evaluate(self.portfolio)
        record_risk(
            exposure_pct=float(exposure),
            daily_loss_pct=float(daily_loss),
            drawdown_pct=float(state.max_drawdown_pct),
            kill_switch=bool(active),
            concentration_pct=0.0,
        )

    def _drawdown_scale(self) -> Decimal:
        dd = self.portfolio.get_state().max_drawdown
        start = self.limits.drawdown_scale_start_pct
        floor = self.limits.drawdown_scale_floor_pct
        if dd <= start or start <= 0:
            return Decimal("1")
        max_dd = self.limits.max_drawdown_pct
        if max_dd <= start:
            return Decimal("1")
        progress = min((dd - start) / (max_dd - start), Decimal("1"))
        scale = Decimal("1") - (Decimal("1") - floor) * progress
        return max(scale, floor)

    def _get_reference_price(self, symbol: str) -> Decimal | None:
        history = self._price_history.get(symbol)
        if not history:
            return None
        cutoff = time() - 300
        recent = [p for ts, p in history if ts >= cutoff]
        if not recent:
            return None
        return sum(recent) / Decimal(len(recent))

    def _record_price(self, symbol: str, price: Decimal) -> None:
        history = self._price_history.setdefault(symbol, deque(maxlen=100))
        history.append((time(), price))


_risk_manager: RiskManager | None = None


def get_risk_manager() -> RiskManager:
    global _risk_manager
    if _risk_manager is None:
        _risk_manager = RiskManager()
    return _risk_manager


def reset_risk_manager() -> None:
    """Reset the global risk manager (used by tests)."""
    global _risk_manager
    _risk_manager = None


__all__ = ["RiskCheckResult", "RiskManager", "get_risk_manager", "reset_risk_manager"]
