"""Tests for Transaction Cost Model."""

from __future__ import annotations

from decimal import Decimal

import pytest

from cryptobot.execution.costs import (
    FeeSchedule,
    FundingConfig,
    FundingModel,
    RebateConfig,
    SlippageConfig,
    SpreadCostConfig,
    TransactionCostConfig,
    TransactionCostModel,
    create_cost_config_from_settings,
    estimate_total_cost_bps,
)


def test_fee_schedule_flat():
    """Test flat fee schedule."""
    fees = FeeSchedule(maker_fee_bps=Decimal("1"), taker_fee_bps=Decimal("5"))

    # Maker fee
    assert fees.get_fees(True) == Decimal("1")
    fee = fees.calculate_fee(Decimal("10000"), True)
    assert fee == Decimal("1.0")  # 10000 * 1 / 10000 = 1

    # Taker fee
    assert fees.get_fees(False) == Decimal("5")
    fee = fees.calculate_fee(Decimal("10000"), False)
    assert fee == Decimal("5.0")  # 10000 * 5 / 10000 = 5


def test_fee_schedule_tiered():
    """Test tiered fee schedule."""
    fees = FeeSchedule(
        maker_fee_bps=Decimal("1"),
        taker_fee_bps=Decimal("5"),
        fee_type="tiered",
        tiers=[
            {"volume_30d": 100000, "maker_bps": Decimal("0.5"), "taker_bps": Decimal("3")},
            {"volume_30d": 1000000, "maker_bps": Decimal("0"), "taker_bps": Decimal("2")},
        ],
    )

    # Below first tier
    assert fees.get_fees(False, Decimal("50000")) == Decimal("5")

    # First tier
    assert fees.get_fees(False, Decimal("500000")) == Decimal("3")
    assert fees.get_fees(True, Decimal("500000")) == Decimal("0.5")

    # Second tier
    assert fees.get_fees(False, Decimal("2000000")) == Decimal("2")
    assert fees.get_fees(True, Decimal("2000000")) == Decimal("0")


def test_slippage_fixed():
    """Test fixed slippage model."""
    config = SlippageConfig(model="fixed_bps", base_slippage_bps=Decimal("5"))

    # Test calculation (would need TransactionCostModel)
    assert config.base_slippage_bps == Decimal("5")


def test_slippage_volatility_adjusted():
    """Test volatility-adjusted slippage."""
    config = SlippageConfig(
        model="volatility_adjusted",
        base_slippage_bps=Decimal("2"),
        vol_multiplier=Decimal("1.5"),
        max_slippage_bps=Decimal("50"),
    )

    # Test: vol=0.02 (2%), base=2, mult=1.5
    # slippage = 2 + 0.02 * 1.5 * 10000 = 2 + 300 = 302 -> capped at 50
    assert config.max_slippage_bps == Decimal("50")


def test_spread_cost_config():
    """Test spread cost configuration."""
    config = SpreadCostConfig(
        cross_spread_pct=Decimal("0.5"),
        use_realtime_spread=True,
        fixed_spread_bps=Decimal("2"),
    )

    assert config.cross_spread_pct == Decimal("0.5")
    assert config.use_realtime_spread is True


def test_funding_config():
    """Test funding rate configuration."""
    config = FundingConfig(
        model=FundingModel.MARKET_BASED,
        fixed_rate=Decimal("0.0001"),
        funding_interval_hours=8,
    )

    assert config.model == FundingModel.MARKET_BASED
    assert config.fixed_rate == Decimal("0.0001")


def test_transaction_cost_model():
    """Test full transaction cost model."""
    config = TransactionCostConfig()
    model = TransactionCostModel(config)

    costs = model.calculate_total_cost(
        symbol="BTCUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity=Decimal("1"),
        price=Decimal("50000"),
        mark_price=Decimal("50000"),
        volatility=Decimal("0.02"),
        daily_volume=Decimal("1000000"),
        spread=Decimal("1"),
        is_maker=True,
        volume_30d=Decimal("1000000"),
        position_side="FLAT",
        holding_hours=0,
    )

    assert "total" in costs
    assert "fee" in costs
    assert "spread" in costs
    assert "slippage" in costs
    assert "total_bps" in costs
    assert costs["total"] >= Decimal("0")


def test_estimate_total_cost_bps():
    """Test quick cost estimation."""
    cost_bps = estimate_total_cost_bps(
        symbol="BTCUSDT",
        side="BUY",
        order_type="MARKET",
        quantity=Decimal("1"),
        price=Decimal("50000"),
        mark_price=Decimal("50000"),
    )

    assert isinstance(cost_bps, Decimal)
    assert cost_bps >= Decimal("0")


def test_create_cost_config_from_settings():
    """Test creating config from settings dict."""
    settings = {
        "maker_fee_bps": "0.5",
        "taker_fee_bps": "3",
        "slippage_model": "volatility_adjusted",
        "base_slippage_bps": "3",
        "use_realtime_spread": "true",
        "fixed_spread_bps": "1",
        "funding_model": "market_based",
        "funding_rate": "0.0001",
        "rebate_enabled": "true",
        "rebate_bps": "1",
    }

    config = create_cost_config_from_settings(settings)

    assert config.fees.maker_fee_bps == Decimal("0.5")
    assert config.fees.taker_fee_bps == Decimal("3")
    assert config.slippage.model.value == "volatility_adjusted"
    assert config.slippage.base_slippage_bps == Decimal("3")


def test_fee_schedule_volume_discount():
    """Test volume discount fee structure."""
    fees = FeeSchedule(
        maker_fee_bps=Decimal("2"),
        taker_fee_bps=Decimal("6"),
        fee_type="volume_discount",
    )

    # Should use base fees when no volume provided
    assert fees.get_fees(False) == Decimal("6")
    assert fees.get_fees(True) == Decimal("2")

    # With volume
    fee = fees.calculate_fee(Decimal("10000"), False, Decimal("500000"))
    # Default still uses base fees
    assert fee == Decimal("6.0")


def test_market_impact_calculation():
    """Test market impact calculation."""
    from decimal import Decimal

    from cryptobot.execution.costs import TransactionCostConfig, TransactionCostModel

    config = TransactionCostConfig()
    model = TransactionCostModel(config)

    # Test with high participation
    impact_cost, impact_bps = model._calculate_market_impact(
        notional=Decimal("100000"),
        daily_volume=Decimal("1000000"),
        volatility=Decimal("0.02"),
        side="BUY",
    )

    assert impact_cost >= Decimal("0")
    assert impact_bps >= Decimal("0")


def test_funding_cost_calculation():
    """Test funding cost calculation."""
    from decimal import Decimal

    from cryptobot.execution.costs import FundingConfig, TransactionCostConfig, TransactionCostModel

    config = TransactionCostConfig(
        funding=FundingConfig(
            model=FundingModel.FIXED,
            fixed_rate=Decimal("0.0001"),
            funding_interval_hours=8,
        )
    )
    model = TransactionCostModel(config)

    # Long position for 24 hours (3 intervals)
    cost = model._calculate_funding_cost(
        notional=Decimal("10000"),
        side="BUY",
        position_side="LONG",
        holding_hours=24,
    )

    # 3 intervals * 0.0001 * 10000 = 3
    assert cost == Decimal("3.0000")


def test_maker_rebate():
    """Test maker rebate calculation."""
    from decimal import Decimal

    from cryptobot.execution.costs import TransactionCostConfig, TransactionCostModel

    config = TransactionCostConfig(
        rebate=RebateConfig(enabled=True, rebate_bps=Decimal("1"))
    )
    model = TransactionCostModel(config)

    rebate = model._calculate_rebate(Decimal("10000"))
    # 10000 * 1 / 10000 = 1, negative = rebate received
    assert rebate == Decimal("-1.0000")


def test_bounds_enforcement():
    """Test cost bounds enforcement."""
    from decimal import Decimal

    from cryptobot.execution.costs import TransactionCostConfig, TransactionCostModel

    config = TransactionCostConfig(
        min_cost_bps=Decimal("1"),
        max_cost_bps=Decimal("100"),
    )
    model = TransactionCostModel(config)

    # Very low cost should be scaled up
    costs = {
        "fee": Decimal("0.1"),
        "spread": Decimal("0"),
        "slippage": Decimal("0"),
        "market_impact": Decimal("0"),
        "funding": Decimal("0"),
        "rebate": Decimal("0"),
        "total": Decimal("0.1"),
        "total_bps": Decimal("0.5"),
    }

    bounded = model._apply_bounds(costs, Decimal("10000"))
    assert bounded["total_bps"] >= Decimal("1")


def test_estimate_total_cost_bps_helper():
    """Test helper function."""
    from decimal import Decimal

    from cryptobot.execution.costs import estimate_total_cost_bps

    cost_bps = estimate_total_cost_bps(
        symbol="BTCUSDT",
        side="SELL",
        order_type="LIMIT",
        quantity=Decimal("0.5"),
        price=Decimal("40000"),
        mark_price=Decimal("40000"),
    )

    assert isinstance(cost_bps, Decimal)
    assert cost_bps >= Decimal("0")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
