from __future__ import annotations

from decimal import Decimal

from cryptobot.backtest.simulator import (
    FillParams,
    FillResult,
    FillSimulator,
    FillSimulatorFactory,
)


def test_fill_params_defaults():
    fp = FillParams()
    assert fp.commission_bps == Decimal("5")
    assert fp.slippage_bps == Decimal("3")
    assert fp.max_slippage_bps == Decimal("20")
    assert fp.funding_rate_included is True
    assert fp.min_order_size == Decimal("10")
    assert fp.max_order_size == Decimal("10000")


def test_fill_result_creation():
    fr = FillResult(
        fill_price=Decimal("100"),
        fill_quantity=Decimal("1"),
        commission=Decimal("0.5"),
        slippage_bps=Decimal("3"),
        fill_time=None,
        is_partial=False,
        is_maker=True,
    )
    assert fr.fill_price == Decimal("100")
    assert fr.funding_payment is None


def test_fill_simulator_update_volatility():
    fs = FillSimulator()
    fs.update_volatility("BTCUSDT", 0.05)
    assert fs._volatility["BTCUSDT"] == Decimal("0.05")


def test_fill_simulator_update_order_book():
    fs = FillSimulator()
    # Mock order book
    class MockOB:
        symbol = "BTCUSDT"
        mid_price = Decimal("100")
        bids = [type("L", (), {"quantity": Decimal("5")})()]
        asks = [type("L", (), {"quantity": Decimal("5")})()]

    fs.update_order_book(MockOB())
    assert "BTCUSDT" in fs._order_book


def test_fill_simulator_calculate_slippage():
    fs = FillSimulator()
    slippage = fs._calculate_slippage("BTCUSDT", "BUY", Decimal("1"), Decimal("100"))
    assert slippage >= Decimal("0")
    assert slippage <= Decimal("20")


def test_fill_simulator_market_impact_slippage():
    fs = FillSimulator()
    # Large order should have more slippage
    small = fs._calculate_slippage("BTCUSDT", "BUY", Decimal("1"), Decimal("100"))
    large = fs._calculate_slippage("BTCUSDT", "BUY", Decimal("1000"), Decimal("100"))
    assert large >= small


def test_fill_simulator_calculate_total_cost():
    fs = FillSimulator()
    fr = FillResult(
        fill_price=Decimal("100"),
        fill_quantity=Decimal("1"),
        commission=Decimal("0.5"),
        slippage_bps=Decimal("3"),
        fill_time=None,
    )
    cost = fs.calculate_total_cost(fr, Decimal("1"))
    assert cost == Decimal("100.5")


def test_fill_simulator_calculate_realized_pnl():
    fs = FillSimulator()
    pnl_long = fs.calculate_realized_pnl(Decimal("100"), Decimal("110"), Decimal("1"), "BUY")
    pnl_short = fs.calculate_realized_pnl(Decimal("110"), Decimal("100"), Decimal("1"), "SELL")
    assert pnl_long == Decimal("10")
    assert pnl_short == Decimal("10")


def test_fill_simulator_factory_backtest():
    fs = FillSimulatorFactory.create_for_backtest(commission_bps=10, slippage_bps=5)
    assert fs.params.commission_bps == Decimal("10")
    assert fs.params.slippage_bps == Decimal("5")


def test_fill_simulator_factory_paper():
    fs = FillSimulatorFactory.create_for_paper(commission_bps=8, slippage_bps=4)
    assert fs.params.commission_bps == Decimal("8")
    assert fs.params.slippage_bps == Decimal("4")


def test_fill_simulator_factory_live():
    fs = FillSimulatorFactory.create_for_live(commission_bps=8, max_slippage_bps=30)
    assert fs.params.max_slippage_bps == Decimal("30")


def test_create_fill_simulator():
    fs = FillSimulatorFactory.create_for_backtest()
    assert isinstance(fs, FillSimulator)


__all__ = []
