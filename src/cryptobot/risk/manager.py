from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from cryptobot.core.events import OrderEvent, RiskEvent
from cryptobot.core.portfolio import PortfolioManager, get_portfolio_manager
from cryptobot.risk.kill_switch import KillSwitch
from cryptobot.risk.limits import RiskLimits


@dataclass
class RiskCheckResult:
    passed: bool
    message: str = ""
    current_value: Optional[Decimal] = None
    limit_value: Optional[Decimal] = None

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

    def check_order(self, order: OrderEvent, price: Optional[Decimal] = None) -> RiskCheckResult:
        active, reason = self.kill_switch.evaluate(self.portfolio)
        if active:
            return RiskCheckResult(False, reason)

        notional_price = price or order.price or order.avg_fill_price
        if notional_price is not None and notional_price > 0:
            notional = order.quantity * notional_price
            if notional < self.limits.min_order_size_usd:
                return RiskCheckResult(False, "Order below minimum size", notional, self.limits.min_order_size_usd)
            if notional > self.limits.max_order_size_usd:
                return RiskCheckResult(False, "Order above maximum size", notional, self.limits.max_order_size_usd)

        state = self.portfolio.get_state()
        if state.total_equity > 0:
            total_exposure = (state.used_margin + (notional if notional_price is not None and notional_price > 0 else Decimal("0"))) / state.total_equity
            if total_exposure > self.limits.max_total_exposure_pct:
                return RiskCheckResult(False, "Total exposure limit exceeded", total_exposure, self.limits.max_total_exposure_pct)

        return RiskCheckResult(True, "OK")


_risk_manager: Optional[RiskManager] = None


def get_risk_manager() -> RiskManager:
    global _risk_manager
    if _risk_manager is None:
        _risk_manager = RiskManager()
    return _risk_manager


__all__ = ["RiskCheckResult", "RiskManager", "get_risk_manager"]
