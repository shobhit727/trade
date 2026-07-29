from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cryptobot.config import settings


@dataclass(frozen=True)
class RiskLimits:
    max_total_exposure_pct: Decimal = Decimal(str(settings.risk.max_total_exposure_pct))
    max_single_position_pct: Decimal = Decimal(str(settings.risk.max_single_position_pct))
    max_daily_loss_pct: Decimal = Decimal(str(settings.risk.max_daily_loss_pct))
    max_drawdown_pct: Decimal = Decimal(str(settings.risk.max_drawdown_pct))
    min_order_size_usd: Decimal = Decimal(str(settings.risk.min_order_size_usd))
    max_order_size_usd: Decimal = Decimal(str(settings.risk.max_order_size_usd))


__all__ = ["RiskLimits"]
