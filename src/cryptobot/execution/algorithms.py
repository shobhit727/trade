from __future__ import annotations

from decimal import Decimal


def twap_slices(quantity: Decimal, periods: int) -> list[Decimal]:
    if periods <= 0 or quantity <= 0:
        return []
    base = quantity / Decimal(periods)
    slices = [base] * periods
    slices[-1] += quantity - sum(slices)
    return slices


def vwap_slices(quantity: Decimal, volume_profile: list[Decimal]) -> list[Decimal]:
    total_volume = sum(volume_profile)
    if quantity <= 0 or total_volume <= 0:
        return []
    slices = [quantity * (v / total_volume) for v in volume_profile]
    slices[-1] += quantity - sum(slices)
    return slices


def pov_quantity(market_volume: Decimal, participation_rate: Decimal, remaining_quantity: Decimal) -> Decimal:
    if market_volume <= 0 or participation_rate <= 0 or remaining_quantity <= 0:
        return Decimal("0")
    return min(market_volume * participation_rate, remaining_quantity)


__all__ = ["pov_quantity", "twap_slices", "vwap_slices"]
