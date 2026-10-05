"""Capital allocator — equity-tiered strategy activation (Seed Phase step 3).

As account equity grows, more algorithms are activated per the agreed tier
ladder (PROJECT_MEMORY/28). Tiers are data, not code: they load from a YAML
file so thresholds can be retuned from paper/live evidence without touching
the trading process.

The global fund's balance is *not* allocatable — the allocator only ever
sees trading equity (total equity minus fund balance).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StrategyAllocation:
    """One algorithm's share of allocatable equity."""

    name: str
    weight: Decimal  # fraction of allocatable equity, tiers sum to <= 1

    def capital_for(self, allocatable_equity: Decimal) -> Decimal:
        return (allocatable_equity * self.weight).quantize(Decimal("0.01"))


@dataclass(frozen=True)
class AllocationTier:
    """Strategies active while ``min_equity <= equity < max_equity``."""

    min_equity: Decimal
    max_equity: Decimal | None  # None = unbounded top tier
    strategies: tuple[StrategyAllocation, ...]
    label: str = ""

    def contains(self, equity: Decimal) -> bool:
        if equity < self.min_equity:
            return False
        return self.max_equity is None or equity < self.max_equity


class CapitalAllocator:
    """Picks the active strategy set + capital shares for a given equity."""

    def __init__(self, tiers: list[AllocationTier]):
        if not tiers:
            raise ValueError("allocator requires at least one tier")
        for t in tiers:
            total = sum((s.weight for s in t.strategies), Decimal("0"))
            if total > Decimal("1"):
                raise ValueError(
                    f"tier '{t.label}' weights sum to {total} (> 1.0); "
                    "over-allocation is not permitted"
                )
        self.tiers = sorted(tiers, key=lambda t: t.min_equity)

    def tier_for(self, equity: Decimal) -> AllocationTier | None:
        for tier in self.tiers:
            if tier.contains(equity):
                return tier
        return None

    def allocate(self, equity: Decimal) -> list[StrategyAllocation]:
        tier = self.tier_for(equity)
        return list(tier.strategies) if tier else []

    def describe(self, equity: Decimal) -> dict:
        tier = self.tier_for(equity)
        if tier is None:
            return {"tier": None, "allocatable_equity": str(equity), "strategies": []}
        return {
            "tier": tier.label or str(tier.min_equity),
            "allocatable_equity": str(equity),
            "strategies": [
                {"name": s.name, "weight": str(s.weight),
                 "capital": str(s.capital_for(equity))}
                for s in tier.strategies
            ],
        }


# ------------------------------------------------------------------ defaults

def default_tiers() -> list[AllocationTier]:
    """Agreed starting ladder (rupees); retune from evidence, not vibes."""
    return [
        AllocationTier(
            min_equity=Decimal("0"), max_equity=Decimal("50000"),
            strategies=(StrategyAllocation("dual_ma", Decimal("1.0")),),
            label="seed",
        ),
        AllocationTier(
            min_equity=Decimal("50000"), max_equity=Decimal("200000"),
            strategies=(
                StrategyAllocation("dual_ma", Decimal("0.6")),
                StrategyAllocation("trend_following", Decimal("0.4")),
            ),
            label="growth",
        ),
        AllocationTier(
            min_equity=Decimal("200000"), max_equity=None,
            strategies=(
                StrategyAllocation("dual_ma", Decimal("0.4")),
                StrategyAllocation("trend_following", Decimal("0.3")),
                StrategyAllocation("ml_ensemble", Decimal("0.3")),
            ),
            label="scale",
        ),
    ]


# ---------------------------------------------------------------- yaml loading

def load_allocator(path: str | Path) -> CapitalAllocator:
    """Build an allocator from YAML:

    allocator:
      tiers:
        - label: seed
          min_equity: "0"
          max_equity: "50000"
          strategies:
            - {name: dual_ma, weight: "1.0"}
    """
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    block = data.get("allocator")
    if not block or not block.get("tiers"):
        logger.warning("no allocator.tiers in %s; using defaults", path)
        return CapitalAllocator(default_tiers())

    tiers: list[AllocationTier] = []
    for raw in block["tiers"]:
        strategies = tuple(
            StrategyAllocation(name=str(s["name"]), weight=Decimal(str(s["weight"])))
            for s in raw.get("strategies", [])
        )
        tiers.append(AllocationTier(
            min_equity=Decimal(str(raw["min_equity"])),
            max_equity=Decimal(str(raw["max_equity"])) if raw.get("max_equity") is not None else None,
            strategies=strategies,
            label=str(raw.get("label", "")),
        ))
    return CapitalAllocator(tiers)


__all__ = [
    "AllocationTier",
    "CapitalAllocator",
    "StrategyAllocation",
    "default_tiers",
    "load_allocator",
]
