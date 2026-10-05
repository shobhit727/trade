"""Unit tests for the capital allocator (Seed Phase step 3)."""

from decimal import Decimal

import pytest

from cryptobot.core.allocator import (
    AllocationTier,
    CapitalAllocator,
    StrategyAllocation,
    default_tiers,
    load_allocator,
)


def test_seed_tier_single_strategy():
    alloc = CapitalAllocator(default_tiers())
    picks = alloc.allocate(Decimal("10000"))
    assert [p.name for p in picks] == ["dual_ma"]
    assert picks[0].capital_for(Decimal("10000")) == Decimal("10000.00")


def test_growth_tier_boundary_inclusive_min():
    alloc = CapitalAllocator(default_tiers())
    tier = alloc.tier_for(Decimal("50000"))
    assert tier.label == "growth"  # min is inclusive
    names = {p.name for p in alloc.allocate(Decimal("50000"))}
    assert names == {"dual_ma", "trend_following"}


def test_scale_tier_top_unbounded():
    alloc = CapitalAllocator(default_tiers())
    assert alloc.tier_for(Decimal("200000")).label == "scale"
    assert alloc.tier_for(Decimal("999999999")).label == "scale"


def test_below_first_tier_returns_empty():
    tiers = [AllocationTier(min_equity=Decimal("1000"), max_equity=None,
                            strategies=(StrategyAllocation("dual_ma", Decimal("1")),),
                            label="gated")]
    alloc = CapitalAllocator(tiers)
    assert alloc.allocate(Decimal("500")) == []
    assert alloc.tier_for(Decimal("500")) is None


def test_weights_over_one_rejected():
    bad = AllocationTier(
        min_equity=Decimal("0"), max_equity=None,
        strategies=(
            StrategyAllocation("a", Decimal("0.7")),
            StrategyAllocation("b", Decimal("0.7")),
        ),
        label="bad",
    )
    with pytest.raises(ValueError, match="over-allocation"):
        CapitalAllocator([bad])


def test_capital_rounding_to_paise():
    s = StrategyAllocation("x", Decimal("0.333"))
    assert s.capital_for(Decimal("1000")) == Decimal("333.00")


def test_describe_shape():
    alloc = CapitalAllocator(default_tiers())
    d = alloc.describe(Decimal("60000"))
    assert d["tier"] == "growth"
    assert d["allocatable_equity"] == "60000"
    caps = {s["name"]: Decimal(s["capital"]) for s in d["strategies"]}
    assert caps["dual_ma"] == Decimal("36000.00")
    assert caps["trend_following"] == Decimal("24000.00")


def test_describe_no_tier():
    tiers = [AllocationTier(min_equity=Decimal("100"), max_equity=Decimal("200"),
                            strategies=(StrategyAllocation("a", Decimal("1")),))]
    d = CapitalAllocator(tiers).describe(Decimal("50"))
    assert d["tier"] is None
    assert d["strategies"] == []


def test_load_allocator_from_yaml(tmp_path):
    yml = tmp_path / "alloc.yaml"
    yml.write_text(
        """
allocator:
  tiers:
    - label: tiny
      min_equity: "0"
      max_equity: "100"
      strategies:
        - {name: dual_ma, weight: "1.0"}
    - label: big
      min_equity: "100"
      max_equity: null
      strategies:
        - {name: dual_ma, weight: "0.5"}
        - {name: trend_following, weight: "0.5"}
""",
        encoding="utf-8",
    )
    alloc = load_allocator(yml)
    assert alloc.tier_for(Decimal("99")).label == "tiny"
    assert alloc.tier_for(Decimal("100")).label == "big"
    assert len(alloc.allocate(Decimal("100"))) == 2


def test_load_allocator_missing_block_falls_back(tmp_path):
    yml = tmp_path / "empty.yaml"
    yml.write_text("other: {}\n", encoding="utf-8")
    alloc = load_allocator(yml)
    assert alloc.tier_for(Decimal("10")).label == "seed"  # defaults


def test_load_allocator_yaml_overweight_rejected(tmp_path):
    yml = tmp_path / "bad.yaml"
    yml.write_text(
        """
allocator:
  tiers:
    - label: greedy
      min_equity: "0"
      max_equity: null
      strategies:
        - {name: a, weight: "0.9"}
        - {name: b, weight: "0.9"}
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="over-allocation"):
        load_allocator(yml)
