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
    max_correlation: Decimal = Decimal(str(settings.risk.max_correlation))
    kill_switch_enabled: bool = settings.risk.kill_switch_enabled
    kill_switch_daily_loss_pct: Decimal = Decimal(str(settings.risk.kill_switch_daily_loss_pct))
    min_order_size_usd: Decimal = Decimal(str(settings.risk.min_order_size_usd))
    max_order_size_usd: Decimal = Decimal(str(settings.risk.max_order_size_usd))
    max_leverage: Decimal = Decimal(str(settings.risk.max_leverage))
    max_open_positions: int = settings.risk.max_open_positions
    price_deviation_pct: Decimal = Decimal(str(settings.risk.price_deviation_pct))
    max_orders_per_minute: int = settings.risk.max_orders_per_minute
    require_stop_loss_above_usd: Decimal = Decimal(str(settings.risk.require_stop_loss_above_usd))
    drawdown_scale_start_pct: Decimal = Decimal(str(settings.risk.drawdown_scale_start_pct))
    drawdown_scale_floor_pct: Decimal = Decimal(str(settings.risk.drawdown_scale_floor_pct))


__all__ = ["RiskLimits"]
