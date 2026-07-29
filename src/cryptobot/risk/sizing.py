from __future__ import annotations

from decimal import Decimal

from cryptobot.config import settings


def fixed_fraction_size(equity: Decimal, fraction: Decimal, price: Decimal) -> Decimal:
    if price <= 0 or equity <= 0 or fraction <= 0:
        return Decimal("0")
    return (equity * fraction) / price


def volatility_target_size(equity: Decimal, target_vol: Decimal, observed_vol: Decimal, price: Decimal) -> Decimal:
    if observed_vol <= 0:
        return fixed_fraction_size(equity, Decimal(str(settings.risk.max_single_position_pct)), price)
    return fixed_fraction_size(equity, min(target_vol / observed_vol, Decimal("1")), price)


def kelly_size(equity: Decimal, win_rate: Decimal, win_loss_ratio: Decimal, price: Decimal) -> Decimal:
    if price <= 0 or win_loss_ratio <= 0:
        return Decimal("0")
    edge = win_rate - ((Decimal("1") - win_rate) / win_loss_ratio)
    fraction = max(Decimal("0"), edge) * Decimal(str(settings.risk.kelly_fraction))
    return fixed_fraction_size(equity, min(fraction, Decimal(str(settings.risk.max_single_position_pct))), price)


__all__ = ["fixed_fraction_size", "volatility_target_size", "kelly_size"]
