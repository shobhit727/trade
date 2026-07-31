from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

TWAP_DEFAULT_PERIODS = 12
VWAP_DEFAULT_SLICES = 12


def twap_slices(quantity: Decimal, periods: int) -> list[Decimal]:
    if periods <= 0 or quantity <= 0:
        return []
    base = quantity / Decimal(periods)
    slices = [base] * periods
    slices[-1] += quantity - sum(slices)
    return slices


def vwap_slices(quantity: Decimal, volume_profile: Sequence[Decimal]) -> list[Decimal]:
    total_volume = sum(volume_profile)
    if quantity <= 0 or total_volume <= 0:
        return []
    slices = [quantity * (Decimal(str(v)) / total_volume) for v in volume_profile]
    slices[-1] += quantity - sum(slices)
    return slices


def pov_quantity(
    market_volume: Decimal,
    participation_rate: Decimal,
    remaining_quantity: Decimal,
    cap: Decimal | None = None,
) -> Decimal:
    if market_volume <= 0 or participation_rate <= 0 or remaining_quantity <= 0:
        return Decimal("0")
    target = market_volume * participation_rate
    if cap is not None:
        target = min(target, cap)
    return min(max(target, Decimal("0")), remaining_quantity)


def pov_quantity_randomized(
    market_volume: Decimal,
    participation_rate: Decimal,
    remaining_quantity: Decimal,
    jitter: float = 0.25,
    seed: int | None = None,
) -> Decimal:
    raw = pov_quantity(market_volume, participation_rate, remaining_quantity)
    if raw <= 0:
        return Decimal("0")
    rng = random.Random(seed)
    factor = 1.0 + rng.uniform(-jitter, jitter)
    raw_with_jitter = Decimal(str(float(raw) * factor))
    return min(raw_with_jitter, remaining_quantity)


def implementation_shortfall_slices(
    quantity: Decimal,
    duration_periods: int = TWAP_DEFAULT_PERIODS,
    arrival_fraction: float = 0.10,
    alpha: float = 1.5,
) -> list[Decimal]:
    """Perée-Clark-style implementation shortfall slicing.

    Front-loads the parent quantity: ``arrival_fraction`` of total goes first,
    the rest decays as ``t^(-alpha)`` but never below zero. Last slice absorbs
    residual rounding.
    """
    if duration_periods <= 0 or quantity <= 0:
        return []
    arrival = max(0.0, min(1.0, arrival_fraction))
    front = quantity * Decimal(str(arrival))
    remaining = quantity - front
    if duration_periods == 1 or remaining <= 0:
        return [quantity]
    n_tail = duration_periods - 1
    raw = [1.0 / ((i + 1) ** alpha) for i in range(n_tail)]
    total = sum(raw)
    if total <= 0:
        return [quantity / Decimal(duration_periods)] * duration_periods
    slices_tail = [Decimal(str(v / total)) * remaining for v in raw]
    slices_tail[-1] += remaining - sum(slices_tail)
    slices = [front] + slices_tail
    slices[-1] += quantity - sum(slices)
    return slices


@dataclass
class IcebergConfig:
    display_quantity: Decimal
    randomization: float = 0.0
    cap: Decimal | None = None

    def __post_init__(self):
        if self.display_quantity <= 0:
            raise ValueError("display_quantity must be > 0")
        if not 0.0 <= self.randomization <= 1.0:
            raise ValueError("randomization must be in [0, 1]")


def iceberg_slices(
    quantity: Decimal,
    config: IcebergConfig,
    seed: int | None = None,
) -> list[Decimal]:
    if quantity <= 0:
        return []
    rng = random.Random(seed) if seed is not None else None
    out: list[Decimal] = []
    remaining = quantity
    while remaining > 0:
        size = config.display_quantity
        if rng is not None and config.randomization > 0:
            size = size * Decimal(str(1.0 + rng.uniform(-config.randomization, config.randomization)))
            if size < Decimal("0.0001"):
                size = config.display_quantity
        if config.cap is not None:
            size = min(size, config.cap)
        size = min(size, remaining)
        out.append(size)
        remaining -= size
    return out


@dataclass
class VWAPSchedule:
    slices: list[Decimal]
    total: Decimal
    is_constant_volume: bool = False
    horizon_minutes: int = 0

    def at(self, minute: int) -> Decimal:
        if not self.slices:
            return Decimal("0")
        if self.horizon_minutes <= 0 or len(self.slices) == 1:
            return self.slices[0]
        if minute >= self.horizon_minutes:
            return Decimal("0")
        per_minute = len(self.slices) / self.horizon_minutes
        if per_minute <= 0:
            return Decimal("0")
        idx = int(minute * per_minute / self.horizon_minutes * len(self.slices))
        idx = max(0, min(idx, len(self.slices) - 1))
        return self.slices[idx]


def vwap_schedule(
    quantity: Decimal,
    volume_profile: Sequence[Decimal],
    horizon_minutes: int,
) -> VWAPSchedule:
    slices = vwap_slices(quantity, volume_profile)
    is_constant = len(set(volume_profile)) == 1
    return VWAPSchedule(
        slices=slices,
        total=quantity,
        is_constant_volume=is_constant,
        horizon_minutes=horizon_minutes,
    )


def liquidity_seek_slices(
    quantity: Decimal,
    levels: Sequence[Decimal],
    level_quantities: Sequence[Decimal],
    fill_probability: float = 0.95,
    seed: int | None = None,
) -> list[Decimal]:
    """Walk the book, slicing the parent across price levels.

    For each level we attempt a fraction proportional to ``min(level_quantity, parent)``
    scaled by ``fill_probability``. Total returned sum <= ``quantity``.
    """
    if quantity <= 0 or not levels or not level_quantities:
        return []
    if len(levels) != len(level_quantities):
        raise ValueError("levels and level_quantities must align")
    p = min(max(fill_probability, 0.0), 1.0)
    rng = random.Random(seed)
    remaining = quantity
    out: list[Decimal] = []
    for lvl_qty in level_quantities:
        if remaining <= 0:
            break
        take = min(Decimal(str(float(lvl_qty) * p)), remaining)
        if rng is not None and rng.random() > p:
            take = take * Decimal("0.5")
        take = min(take, remaining)
        if take > 0:
            out.append(take)
            remaining -= take
    if remaining > 0:
        out.append(remaining)
    return out


def arrival_price_benchmark(price: Decimal, qty: Decimal, fee_bps: Decimal = Decimal("0")) -> Decimal:
    """Perée benchmark = arrival mid - half-spread-equivalent; placeholder here returns
    the supplied price, used by ExecutionEngine when no other benchmark is set."""
    if price <= 0 or qty <= 0:
        return Decimal("0")
    if fee_bps <= 0:
        return price
    return price * (Decimal("1") + fee_bps / Decimal("10000"))


def build_pov_schedule(
    quantity: Decimal,
    duration_periods: int,
    participation_rate: Decimal,
    market_volume_per_period: Decimal,
    cap_per_period: Decimal | None = None,
) -> list[Decimal]:
    if quantity <= 0 or duration_periods <= 0 or market_volume_per_period <= 0:
        return []
    out: list[Decimal] = []
    remaining = quantity
    for _ in range(duration_periods):
        take = pov_quantity(market_volume_per_period, participation_rate, remaining, cap=cap_per_period)
        out.append(take)
        remaining -= take
        if remaining <= 0:
            break
    if remaining > 0 and out:
        # Redistribute the leftover across the remaining periods up to the cap.
        leftover_periods = duration_periods - len(out)
        if leftover_periods > 0:
            per_period = remaining / leftover_periods
            per_period = min(per_period, cap_per_period) if cap_per_period else per_period
            for _ in range(leftover_periods):
                out.append(per_period)
        else:
            out[-1] += remaining
    return out


def slicer_for(name: str):
    mapping = {
        "twap": twap_slices,
        "vwap": vwap_slices,
        "is": implementation_shortfall_slices,
        "iceberg": lambda q, *a, **kw: iceberg_slices(q, *a, **kw) if a else _iceberg_default(q, **kw),
        "pov": lambda q, *a, **kw: build_pov_schedule(q, *a, **kw),
        "liquidity_seek": liquidity_seek_slices,
    }
    if name not in mapping:
        raise ValueError(f"unknown slicer: {name}")
    return mapping[name]


def _iceberg_default(quantity: Decimal, **kwargs):
    if "config" not in kwargs:
        raise TypeError("iceberg requires IcebergConfig")
    return iceberg_slices(quantity, kwargs["config"])


__all__ = [
    "IcebergConfig",
    "TWAP_DEFAULT_PERIODS",
    "VWAP_DEFAULT_SLICES",
    "VWAPSchedule",
    "arrival_price_benchmark",
    "build_pov_schedule",
    "iceberg_slices",
    "implementation_shortfall_slices",
    "liquidity_seek_slices",
    "pov_quantity",
    "pov_quantity_randomized",
    "slicer_for",
    "twap_slices",
    "vwap_schedule",
    "vwap_slices",
]
