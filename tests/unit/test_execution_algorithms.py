from __future__ import annotations

from decimal import Decimal

import pytest

from cryptobot.execution.algorithms import (
    IcebergConfig,
    arrival_price_benchmark,
    build_pov_schedule,
    iceberg_slices,
    implementation_shortfall_slices,
    liquidity_seek_slices,
    pov_quantity,
    pov_quantity_randomized,
    slicer_for,
    twap_slices,
    vwap_schedule,
    vwap_slices,
)


def test_twap_slices_sum_to_total():
    out = twap_slices(Decimal("100"), 5)
    assert len(out) == 5
    assert sum(out) == Decimal("100")


def test_twap_slices_zero_or_negative():
    assert twap_slices(Decimal("0"), 5) == []
    assert twap_slices(Decimal("100"), 0) == []


def test_vwap_slices_proportional_to_profile():
    profile = [Decimal(10), Decimal(30), Decimal(60)]
    slices = vwap_slices(Decimal("100"), profile)
    assert sum(slices) == Decimal("100")
    assert slices[2] >= slices[1] >= slices[0]


def test_vwap_slices_zero_volume_profile():
    assert vwap_slices(Decimal("100"), [Decimal(0)]) == []


def test_pov_quantity_basic_and_cap():
    q = pov_quantity(Decimal("100"), Decimal("0.1"), Decimal("20"))
    assert q == Decimal("10")
    capped = pov_quantity(Decimal("100"), Decimal("0.5"), Decimal("20"), cap=Decimal("3"))
    assert capped == Decimal("3")


def test_pov_quantity_randomized_in_range():
    q = pov_quantity_randomized(
        Decimal("100"), Decimal("0.1"), Decimal("20"), jitter=0.1, seed=42
    )
    assert Decimal("9") <= q <= Decimal("11")


def test_implementation_shortfall_slices_front_loads():
    slices = implementation_shortfall_slices(
        Decimal("100"), duration_periods=10, arrival_fraction=0.20, alpha=1.5
    )
    assert len(slices) == 10
    assert slices[0] >= slices[-1]
    assert sum(slices) == Decimal("100")


def test_implementation_shortfall_slices_handles_edge_cases():
    assert implementation_shortfall_slices(Decimal("0"), 5) == []
    assert implementation_shortfall_slices(Decimal("100"), 0) == []
    short = implementation_shortfall_slices(Decimal("100"), 1, arrival_fraction=0.5)
    assert short == [Decimal("100")]


def test_iceberg_slices_split_by_display_quantity():
    cfg = IcebergConfig(display_quantity=Decimal("3"))
    out = iceberg_slices(Decimal("10"), cfg, seed=0)
    assert len(out) >= 4
    assert all(s == Decimal("3") or s == Decimal("1") for s in out)
    assert sum(out) == Decimal("10")


def test_iceberg_config_validation():
    with pytest.raises(ValueError):
        IcebergConfig(display_quantity=Decimal("0"))
    with pytest.raises(ValueError):
        IcebergConfig(display_quantity=Decimal("1"), randomization=-0.1)


def test_vwap_schedule_constant_volume_flag():
    sched = vwap_schedule(Decimal("100"), [Decimal(10)] * 5, horizon_minutes=30)
    assert sched.is_constant_volume
    assert sum(sched.slices) == Decimal("100")
    assert sched.at(15) > 0


def test_vwap_schedule_at_handles_bounds():
    sched = vwap_schedule(Decimal("100"), [Decimal(1)] * 5, horizon_minutes=5)
    assert sched.at(4) >= sched.at(0)
    assert sched.at(99) == Decimal("0")


def test_liquidity_seek_slices_consumes_levels():
    out = liquidity_seek_slices(
        Decimal("10"),
        levels=[Decimal("100"), Decimal("101"), Decimal("102")],
        level_quantities=[Decimal("4"), Decimal("4"), Decimal("4")],
        fill_probability=1.0,
        seed=1,
    )
    assert sum(out) >= Decimal("10")
    assert sum(out) <= Decimal("12")


def test_liquidity_seek_slices_level_count_mismatch():
    with pytest.raises(ValueError):
        liquidity_seek_slices(
            Decimal("10"),
            levels=[Decimal("100")],
            level_quantities=[Decimal("1"), Decimal("1")],
            fill_probability=0.5,
        )


def test_arrival_price_benchmark_zero_or_no_fee():
    assert arrival_price_benchmark(Decimal("0"), Decimal("1")) == Decimal("0")
    assert arrival_price_benchmark(Decimal("100"), Decimal("0")) == Decimal("0")
    assert arrival_price_benchmark(Decimal("100"), Decimal("1")) == Decimal("100")
    bumped = arrival_price_benchmark(Decimal("100"), Decimal("1"), fee_bps=Decimal("5"))
    assert bumped > Decimal("100")


def test_build_pov_schedule_respects_remaining():
    out = build_pov_schedule(
        Decimal("100"),
        duration_periods=5,
        participation_rate=Decimal("0.1"),
        market_volume_per_period=Decimal("100"),
        cap_per_period=Decimal("8"),
    )
    assert len(out) == 5
    assert all(s <= Decimal("8") for s in out)
    assert sum(out) == Decimal("100")


def test_slicer_for_dispatch():
    fn = slicer_for("twap")
    assert fn(Decimal("10"), 3) == [Decimal("10") / Decimal(3)] * 3
    with pytest.raises(ValueError):
        slicer_for("nope")


def test_slicer_for_iceberg_requires_config():
    fn = slicer_for("iceberg")
    cfg = IcebergConfig(display_quantity=Decimal("2"))
    out = fn(Decimal("5"), config=cfg)
    assert sum(out) == Decimal("5")


def test_slicer_for_pov_dispatch():
    fn = slicer_for("pov")
    out = fn(
        Decimal("10"),
        duration_periods=3,
        participation_rate=Decimal("0.1"),
        market_volume_per_period=Decimal("100"),
    )
    assert sum(out) == Decimal("10")
