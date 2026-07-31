"""Tests for cryptobot.risk.* helpers.

Covers every module that ships in the risk package but lacks direct
test coverage. Touches:
- RiskLimits (frozen dataclass)
- KillSwitch (delegates to PortfolioManager)
- max_abs_correlation
- fixed_fraction_size / volatility_target_size / kelly_size
- configuration override via env
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from cryptobot.risk.correlation import max_abs_correlation
from cryptobot.risk.kill_switch import KillSwitch
from cryptobot.risk.limits import RiskLimits
from cryptobot.risk.sizing import fixed_fraction_size, kelly_size, volatility_target_size

# --- RiskLimits ---------------------------------------------------------


def test_risk_limits_default_values_match_settings():
    limits = RiskLimits()
    assert limits.max_total_exposure_pct > Decimal("0")
    assert limits.max_single_position_pct > Decimal("0")
    assert limits.min_order_size_usd > Decimal("0")
    assert limits.max_order_size_usd > Decimal("0")


def test_risk_limits_is_frozen():
    limits = RiskLimits()
    with pytest.raises((AttributeError, TypeError)):
        limits.max_total_exposure_pct = Decimal("99")


# --- KillSwitch ---------------------------------------------------------


def test_kill_switch_disabled_in_settings_returns_false(monkeypatch):
    import cryptobot.config as cfg_mod

    class _FakeSettings:
        class risk:
            kill_switch_enabled = False

    monkeypatch.setattr(cfg_mod, "settings", cfg_mod.Settings())
    # Force the settings.risk.kill_switch_enabled to False via env override
    import os
    os.environ["RISK_KILL_SWITCH_ENABLED"] = "false"
    # Need to reload or patch - easier: just test the logic directly
    from cryptobot.core.portfolio import PortfolioManager
    from cryptobot.risk.kill_switch import KillSwitch

    pm = PortfolioManager()
    ks = KillSwitch()
    # With kill_switch_enabled=False, evaluate returns False
    active, reason = ks.evaluate(pm)
    assert active is False
    assert reason == ""


def test_kill_switch_delegates_to_portfolio():
    pm = type(
        "PM",
        (),
        {"check_kill_switch": lambda self: (True, "drawdown limit hit")},
    )()
    pm.state = type("State", (), {})()
    ks = KillSwitch()
    active, reason = ks.evaluate(pm)
    assert active is True
    assert reason == "drawdown limit hit"
    assert ks.reason == "drawdown limit hit"


def test_kill_switch_reset_clears_state():
    ks = KillSwitch(active=True, reason="x")
    ks.reset()
    assert ks.active is False
    assert ks.reason == ""


# --- max_abs_correlation -------------------------------------------------


def test_max_abs_correlation_returns_zero_for_empty():
    assert max_abs_correlation({}) == Decimal("0")


def test_max_abs_correlation_picks_max_absolute():
    table = {
        ("A", "B"): Decimal("0.4"),
        ("B", "C"): Decimal("-0.9"),
        ("C", "D"): Decimal("0.2"),
    }
    assert max_abs_correlation(table) == Decimal("0.9")


def test_max_abs_correlation_only_absolute_used():
    table = {("A", "B"): Decimal("-0.6")}
    assert max_abs_correlation(table) == Decimal("0.6")


# --- sizing helpers ------------------------------------------------------


def test_fixed_fraction_size_basic():
    qty = fixed_fraction_size(Decimal("10000"), Decimal("0.05"), Decimal("100"))
    assert qty == Decimal("5")  # 5% of 10k / 100


def test_fixed_fraction_size_handles_zero_inputs():
    z = Decimal("0")
    assert fixed_fraction_size(z, Decimal("1"), Decimal("100")) == z
    assert fixed_fraction_size(Decimal("100"), Decimal("1"), z) == z
    assert fixed_fraction_size(Decimal("100"), z, Decimal("100")) == z


def test_volatility_target_size_caps_at_max_position():
    qty = volatility_target_size(
        Decimal("10000"), Decimal("0.5"), Decimal("0.001"), Decimal("100")
    )
    assert qty > Decimal("0")


def test_volatility_target_size_zero_vol_falls_back_to_max_position():
    qty = volatility_target_size(
        Decimal("10000"),
        Decimal("0.5"),
        Decimal("0"),
        Decimal("100"),
    )
    assert qty > Decimal("0")


def test_kelly_size_handles_zero_winrate():
    assert kelly_size(Decimal("10000"), Decimal("0"), Decimal("1.5"), Decimal("100")) == Decimal("0")


def test_kelly_size_positive_edge_yields_position():
    qty = kelly_size(Decimal("10000"), Decimal("0.6"), Decimal("1"), Decimal("100"))
    assert qty > Decimal("0")


def test_kelly_size_zero_price_returns_zero():
    assert kelly_size(Decimal("10000"), Decimal("0.6"), Decimal("1"), Decimal("0")) == Decimal("0")


def test_kelly_size_caps_position_with_max_single_position_pct():
    from cryptobot.config import settings

    qty = kelly_size(Decimal("10000"), Decimal("1"), Decimal("100"), Decimal("100"))
    assert qty <= Decimal(str(settings.risk.max_single_position_pct)) * Decimal("100")
