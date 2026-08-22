"""Unit tests for risk profiles + vol-targeted sizing (Seed Phase step 6)."""

from decimal import Decimal

import pytest

from cryptobot.core.profiles import (
    AGGRESSIVE,
    REALISTIC,
    get_profile,
    liq_distance_pct,
    vol_targeted_leverage,
)


def test_presets_match_agreed_spec():
    assert REALISTIC.max_leverage == Decimal("1")
    assert AGGRESSIVE.max_leverage == Decimal("3")
    for p in (REALISTIC, AGGRESSIVE):
        assert p.min_liq_distance == 0.25
        assert p.breaker_max_drawdown == Decimal("-0.25")


def test_get_profile_case_insensitive_and_unknown():
    assert get_profile("AGGRESSIVE").name == "aggressive"
    with pytest.raises(ValueError, match="unknown risk profile"):
        get_profile("yolo")


def test_vol_target_scales_inverse_to_vol():
    # calm market: 20% realized vs 80% target -> ~4x, clamped to 3x
    assert vol_targeted_leverage(0.20, AGGRESSIVE) == Decimal("3.0000")
    # wild market: 160% realized -> 0.5x
    assert vol_targeted_leverage(1.60, AGGRESSIVE) == Decimal("0.5000")


def test_vol_target_realistic_never_exceeds_spot():
    assert vol_targeted_leverage(0.05, REALISTIC) <= Decimal("1")
    assert vol_targeted_leverage(0.01, REALISTIC) == Decimal("1.0000")


def test_unknown_vol_is_defensive_not_greedy():
    assert vol_targeted_leverage(None, AGGRESSIVE) == Decimal("1.0000")
    assert vol_targeted_leverage(0.0, AGGRESSIVE) == Decimal("1.0000")
    assert vol_targeted_leverage(-1.0, AGGRESSIVE) == Decimal("1.0000")


def test_liq_distance_guard_clamps():
    # floor 25% => leverage cap 4x; aggressive max is 3x so untouched,
    # but a hypothetical profile with higher cap must clamp to 4x
    from cryptobot.core.profiles import RiskProfile

    wild = RiskProfile("wild", max_leverage=Decimal("10"), target_annual_vol=5.0,
                       min_vol_for_leverage=0.1, min_liq_distance=0.25,
                       breaker_max_drawdown=Decimal("-0.25"))
    lev = vol_targeted_leverage(0.2, wild)   # raw 25x
    assert lev <= Decimal("4")               # 1 / 0.25


def test_liq_distance_math():
    assert liq_distance_pct(Decimal("3")) == pytest.approx(33.333, abs=0.01)
    assert liq_distance_pct(Decimal("1")) == 100.0
    assert liq_distance_pct(Decimal("0")) == float("inf")
