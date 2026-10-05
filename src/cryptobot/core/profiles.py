"""Risk profiles + volatility-targeted sizing (Seed Phase step 6).

Two agreed profiles race in paper:

- ``realistic``: spot-only (leverage capped at 1x), moderate vol target
- ``aggressive``: dynamic volatility-targeted leverage inside hard bounds
  0–3x, always far enough from liquidation (>= 25% price distance)

Sizing rule: ``leverage = target_vol / realized_vol``, clamped to
``[floor, max_leverage]`` and further limited by the liquidation-distance
floor (approximate liquidation at an adverse move of ``1 / leverage``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RiskProfile:
    name: str
    max_leverage: Decimal          # hard ceiling; 1 = spot-only
    target_annual_vol: float       # sizing aims here
    min_vol_for_leverage: float    # below this realized vol, cap out
    min_liq_distance: float        # fraction, e.g. 0.25 = 25%
    breaker_max_drawdown: Decimal  # e.g. -0.25 of peak equity


REALISTIC = RiskProfile(
    name="realistic",
    max_leverage=Decimal("1"),
    target_annual_vol=0.45,
    min_vol_for_leverage=0.10,
    min_liq_distance=0.25,
    breaker_max_drawdown=Decimal("-0.25"),
)

AGGRESSIVE = RiskProfile(
    name="aggressive",
    max_leverage=Decimal("3"),
    target_annual_vol=0.80,
    min_vol_for_leverage=0.10,
    min_liq_distance=0.25,
    breaker_max_drawdown=Decimal("-0.25"),
)

PROFILES: dict[str, RiskProfile] = {p.name: p for p in (REALISTIC, AGGRESSIVE)}


def get_profile(name: str) -> RiskProfile:
    try:
        return PROFILES[name.lower()]
    except KeyError:
        raise ValueError(f"unknown risk profile '{name}'; choose from {sorted(PROFILES)}") from None


def vol_targeted_leverage(realized_annual_vol: float | None, profile: RiskProfile) -> Decimal:
    """Leverage that aims at the profile's vol target, inside all bounds.

    Unknown/zero vol is treated defensively: fall back to 1x (spot-sized),
    never to max.
    """
    if realized_annual_vol is None or realized_annual_vol <= profile.min_vol_for_leverage:
        return min(Decimal("1"), profile.max_leverage)

    raw = profile.target_annual_vol / realized_annual_vol
    lev = min(Decimal(str(round(raw, 4))), profile.max_leverage)
    lev = max(lev, Decimal("0"))
    # Liquidation-distance guard: adverse move wiping the margin is ~1/L;
    # require it to stay beyond the floor by capping leverage.
    liq_cap = Decimal(str(round(1.0 / profile.min_liq_distance, 4)))
    if lev > liq_cap:
        logger.warning("leverage %s exceeds liq-distance cap %s; clamping",
                       lev, liq_cap)
        lev = liq_cap
    return lev.quantize(Decimal("0.0001"))


def liq_distance_pct(leverage: Decimal) -> float:
    """Approximate adverse move (%) that wipes the position's margin."""
    lev = float(leverage)
    if lev <= 0:
        return float("inf")
    return 100.0 / lev


__all__ = [
    "AGGRESSIVE",
    "PROFILES",
    "REALISTIC",
    "RiskProfile",
    "get_profile",
    "liq_distance_pct",
    "vol_targeted_leverage",
]
