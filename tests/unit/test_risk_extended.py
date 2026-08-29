from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from cryptobot.core.events import OrderEvent, OrderSide
from cryptobot.core.portfolio import PortfolioManager, PortfolioMode
from cryptobot.risk.limits import RiskLimits
from cryptobot.risk.manager import RiskManager
from cryptobot.risk.rate_limit import RateLimiter
from cryptobot.risk.strategy_tracker import StrategyRiskTracker


def _limits(**kwargs) -> RiskLimits:
    """Create a RiskLimits with overridden fields (handles frozen dataclass)."""
    base = RiskLimits()
    return replace(base, **kwargs)


def _pm(equity: Decimal = Decimal("10000")) -> PortfolioManager:
    import asyncio
    pm = PortfolioManager(PortfolioMode.BACKTEST)
    asyncio.run(pm.update_equity(equity))
    return pm


# --- RateLimiter ---------------------------------------------------------

def test_rate_limiter_allows_up_to_limit():
    rl = RateLimiter(max_events=3, window_seconds=60)
    assert rl.try_acquire() is True
    assert rl.try_acquire() is True
    assert rl.try_acquire() is True
    assert rl.try_acquire() is False


def test_rate_limiter_resets_after_window():
    rl = RateLimiter(max_events=2, window_seconds=0.01)
    assert rl.try_acquire() is True
    assert rl.try_acquire() is True
    assert rl.try_acquire() is False
    import time
    time.sleep(0.02)
    assert rl.try_acquire() is True


def test_rate_limiter_reset():
    rl = RateLimiter(max_events=1, window_seconds=60)
    assert rl.try_acquire() is True
    assert rl.try_acquire() is False
    rl.reset()
    assert rl.try_acquire() is True


def test_rate_limiter_invalid_args():
    with pytest.raises(ValueError):
        RateLimiter(max_events=0, window_seconds=60)
    with pytest.raises(ValueError):
        RateLimiter(max_events=1, window_seconds=0)


# --- StrategyRiskTracker -------------------------------------------------

def test_strategy_tracker_records_pnl():
    tr = StrategyRiskTracker()
    tr.record_pnl("strat1", Decimal("100"), day_key=1)
    st = tr.get("strat1")
    assert st.total_pnl == Decimal("100")
    assert st.daily_pnl == Decimal("100")
    assert st.peak_equity == Decimal("100")


def test_strategy_tracker_drawdown():
    tr = StrategyRiskTracker()
    tr.record_pnl("strat1", Decimal("100"), day_key=1)
    tr.record_pnl("strat1", Decimal("-20"), day_key=1)
    st = tr.get("strat1")
    assert st.max_drawdown > Decimal("0")


def test_strategy_tracker_reset_daily():
    tr = StrategyRiskTracker()
    tr.record_pnl("strat1", Decimal("100"), day_key=1)
    tr.reset_daily("strat1", Decimal("500"), day_key=2)
    st = tr.get("strat1")
    assert st.daily_pnl == Decimal("0")
    assert st.daily_pnl_start == Decimal("500")


# --- RiskManager new checks ----------------------------------------------

def test_risk_manager_rejects_excess_leverage():
    pm = _pm()
    rm = RiskManager(portfolio=pm, limits=_limits(max_leverage=Decimal("5")))
    order = OrderEvent(
        symbol="BTCUSDT", side=OrderSide.BUY, quantity=Decimal("1"),
        price=Decimal("100"), strategy="test", leverage=10,
    )
    res = rm.check_order(order, price=Decimal("100"))
    assert res.passed is False
    assert "Leverage" in res.message


def test_risk_manager_rejects_excess_open_positions(monkeypatch):
    from cryptobot.core import state as state_mod
    pm = _pm()
    rm = RiskManager(portfolio=pm, limits=_limits(max_open_positions=1))
    class _Pos:
        quantity = Decimal("1")
    monkeypatch.setattr(state_mod.state_manager, "get_positions", lambda: [_Pos()])
    order = OrderEvent(
        symbol="ETHUSDT", side=OrderSide.BUY, quantity=Decimal("1"),
        price=Decimal("100"), strategy="test",
    )
    res = rm.check_order(order, price=Decimal("100"))
    assert res.passed is False
    assert "Max open positions" in res.message


def test_risk_manager_rejects_price_deviation():
    pm = _pm()
    rm = RiskManager(portfolio=pm, limits=_limits(price_deviation_pct=Decimal("0.05")))
    order1 = OrderEvent(
        symbol="BTCUSDT", side=OrderSide.BUY, quantity=Decimal("1"),
        price=Decimal("100"), strategy="test",
    )
    assert rm.check_order(order1, price=Decimal("100")).passed is True
    order2 = OrderEvent(
        symbol="BTCUSDT", side=OrderSide.BUY, quantity=Decimal("1"),
        price=Decimal("111"), strategy="test",
    )
    res = rm.check_order(order2, price=Decimal("111"))
    assert res.passed is False
    assert "deviates" in res.message


def test_risk_manager_rejects_excess_rate():
    pm = _pm()
    rm = RiskManager(portfolio=pm, limits=_limits(max_orders_per_minute=2))
    order = OrderEvent(
        symbol="BTCUSDT", side=OrderSide.BUY, quantity=Decimal("0.1"),
        price=Decimal("100"), strategy="test",
    )
    assert rm.check_order(order, price=Decimal("100")).passed is True
    assert rm.check_order(order, price=Decimal("100")).passed is True
    assert rm.check_order(order, price=Decimal("100")).passed is False


def test_risk_manager_stop_loss_required():
    pm = _pm()
    rm = RiskManager(
        portfolio=pm,
        limits=_limits(
            require_stop_loss_above_usd=Decimal("100"),
            max_total_exposure_pct=Decimal("2.0"),  # High to avoid exposure check
            max_single_position_pct=Decimal("2.0"),
        ),
    )
    order = OrderEvent(
        symbol="BTCUSDT", side=OrderSide.BUY, quantity=Decimal("100"),
        price=Decimal("100"), strategy="test",
    )
    res = rm.check_order(order, price=Decimal("100"))
    assert res.passed is False
    assert "Stop-loss required" in res.message
    order.stop_price = Decimal("95")
    res2 = rm.check_order(order, price=Decimal("100"))
    assert res2.passed is True


def test_risk_manager_correlation_rejection():
    pm = _pm()
    rm = RiskManager(portfolio=pm)
    corr = {("BTCUSDT", "ETHUSDT"): Decimal("0.9")}
    order = OrderEvent(
        symbol="BTCUSDT", side=OrderSide.BUY, quantity=Decimal("1"),
        price=Decimal("100"), strategy="test",
    )
    res = rm.check_order(order, price=Decimal("100"), correlation_matrix=corr)
    assert res.passed is False
    assert "Correlation" in res.message


def test_risk_manager_correlation_within_limit():
    pm = _pm()
    rm = RiskManager(portfolio=pm)
    corr = {("BTCUSDT", "ETHUSDT"): Decimal("0.5")}
    order = OrderEvent(
        symbol="BTCUSDT", side=OrderSide.BUY, quantity=Decimal("1"),
        price=Decimal("100"), strategy="test",
    )
    res = rm.check_order(order, price=Decimal("100"), correlation_matrix=corr)
    assert res.passed is True


def test_risk_manager_strategy_daily_loss():
    pm = _pm()
    # Daily-loss limit is enforced against the portfolio aggregate daily P&L
    # (the per-strategy tracker is not wired to live P&L events).
    pm._state.daily_pnl = Decimal("-600")
    rm = RiskManager(portfolio=pm)
    order = OrderEvent(
        symbol="BTCUSDT", side=OrderSide.BUY, quantity=Decimal("1"),
        price=Decimal("100"), strategy="bad_strat",
    )
    res = rm.check_order(order, price=Decimal("100"))
    assert res.passed is False
    assert "daily loss limit" in res.message


def test_risk_manager_drawdown_scaling():
    pm = _pm()
    pm._state.peak_equity = Decimal("10000")
    pm._state.total_equity = Decimal("9200")
    pm._state.max_drawdown = Decimal("0.08")
    rm = RiskManager(
        portfolio=pm,
        limits=_limits(
            drawdown_scale_start_pct=Decimal("0.05"),
            drawdown_scale_floor_pct=Decimal("0.25"),
            max_single_position_pct=Decimal("0.05"),
            max_total_exposure_pct=Decimal("0.99"),
        ),
    )
    order = OrderEvent(
        symbol="BTCUSDT", side=OrderSide.BUY, quantity=Decimal("20"),
        price=Decimal("100"), strategy="test",
    )
    res = rm.check_order(order, price=Decimal("100"))
    assert res.passed is False
    assert "scaled limit" in res.message


def test_risk_manager_compute_position_size_all_methods():
    pm = _pm()
    rm = RiskManager(portfolio=pm)

    import cryptobot.config as cfg_mod
    original = cfg_mod.settings.risk.position_sizing
    try:
        for method in ("fixed", "volatility_target", "kelly_fraction"):
            cfg_mod.settings.risk.position_sizing = method
            size = rm.compute_position_size(Decimal("10000"), Decimal("100"))
            assert size > Decimal("0")
    finally:
        cfg_mod.settings.risk.position_sizing = original


def test_risk_manager_compute_position_size_with_vol():
    pm = _pm()
    rm = RiskManager(portfolio=pm)
    size = rm.compute_position_size(
        Decimal("10000"), Decimal("100"), observed_vol=Decimal("0.10")
    )
    assert size > Decimal("0")


# --- RiskLimits with new fields ------------------------------------------

def test_risk_limits_new_fields_present():
    limits = RiskLimits()
    assert hasattr(limits, "max_leverage")
    assert hasattr(limits, "max_open_positions")
    assert hasattr(limits, "price_deviation_pct")
    assert hasattr(limits, "max_orders_per_minute")
    assert hasattr(limits, "require_stop_loss_above_usd")
    assert hasattr(limits, "drawdown_scale_start_pct")
    assert hasattr(limits, "drawdown_scale_floor_pct")
    assert hasattr(limits, "max_correlation")
    assert hasattr(limits, "kill_switch_enabled")


__all__ = []
