"""Risk-limit and kill-switch tests.

`GOAL.md` §3.3 is binding and non-negotiable. These tests exist to make it impossible
to quietly widen a limit without the suite going red.
"""

from __future__ import annotations

from decimal import Decimal as D

import pytest

from nsealgo.execution.broker import Position, Quote
from nsealgo.execution.paper import PaperBroker
from nsealgo.risk.limits import (
    LIMITS,
    KillSwitchEngaged,
    RiskLimits,
    RiskLimitViolation,
    RiskManager,
    limits_as_dict,
)


class TestConstitution:
    def test_limits_are_frozen(self) -> None:
        with pytest.raises(Exception):
            LIMITS.max_drawdown_halt = D("0.99")  # type: ignore[misc]

    def test_values_match_goal_md(self) -> None:
        assert LIMITS.max_drawdown_halt == D("0.15")
        assert LIMITS.max_drawdown_absolute == D("0.25")
        assert LIMITS.per_trade_stop == D("0.08")
        assert LIMITS.max_daily_loss == D("0.02")
        assert LIMITS.max_weekly_loss == D("0.04")
        assert LIMITS.max_single_weight == D("0.12")
        assert LIMITS.max_sector_weight == D("0.25")

    def test_verify_catches_a_raised_limit(self) -> None:
        """The core anti-footgun test: constructing widened limits must fail."""
        import dataclasses

        widened = dataclasses.replace(LIMITS, max_daily_loss=D("0.10"))
        with pytest.raises(RiskLimitViolation, match="GOAL.md"):
            widened.verify()

    def test_verify_catches_widened_drawdown(self) -> None:
        import dataclasses

        widened = dataclasses.replace(LIMITS, max_drawdown_halt=D("0.40"))
        with pytest.raises(RiskLimitViolation):
            widened.verify()

    def test_incoherent_position_bounds_rejected(self) -> None:
        bad = RiskLimits(min_positions=50, max_positions=30)
        with pytest.raises(RiskLimitViolation, match="min_positions"):
            bad.verify()

    def test_serialisable(self) -> None:
        d = limits_as_dict()
        assert d["max_daily_loss"] == D("0.02")


class TestKillSwitch:
    def test_drawdown_halt_trips_at_15pct(self) -> None:
        rm = RiskManager()
        rm.update_equity(D("2100000"))
        assert not rm.is_halted
        # Re-baseline day/week so we are testing the drawdown limit in isolation.
        rm.start_day(D("1780000"))
        rm.start_week(D("1780000"))
        rm.update_equity(D("1780000"))          # -15.24% from peak
        assert rm.is_halted
        assert "DRAWDOWN" in rm.kill_switch_reason

    def test_just_under_limit_does_not_trip(self) -> None:
        rm = RiskManager()
        rm.update_equity(D("2100000"))
        rm.start_day(D("1800000"))
        rm.start_week(D("1800000"))
        rm.update_equity(D("1800000"))          # -14.3%
        assert not rm.is_halted

    def test_daily_loss_trips_at_2pct(self) -> None:
        rm = RiskManager()
        rm.update_equity(D("2100000"))
        rm.start_day(D("2100000"))
        rm.update_equity(D("2060000"))          # -1.90%
        assert not rm.is_halted
        rm.update_equity(D("2050000"))          # -2.38% on the day
        assert rm.is_halted
        assert "DAILY LOSS" in rm.kill_switch_reason

    def test_weekly_loss_trips_at_4pct(self) -> None:
        rm = RiskManager()
        rm.update_equity(D("2100000"))
        rm.start_day(D("2010000"))   # isolate weekly: day is already flat
        rm.start_week(D("2100000"))
        rm.update_equity(D("2010000"))          # -4.29% on the week, -0% on the day
        assert rm.is_halted
        assert "WEEKLY LOSS" in rm.kill_switch_reason

    def test_all_breaches_are_recorded_not_just_the_first(self) -> None:
        rm = RiskManager()
        rm.update_equity(D("2100000"))
        rm.update_equity(D("1600000"))          # breaches DD, daily and weekly
        assert len(rm.breached_limits) >= 3

    def test_absolute_drawwdown_takes_precedence_message(self) -> None:
        rm = RiskManager()
        rm.update_equity(D("2100000"))
        rm.start_day(D("1500000"))
        rm.start_week(D("1500000"))
        rm.update_equity(D("1500000"))          # -28.6%
        assert "ABSOLUTE" in rm.kill_switch_reason
        assert len(rm.breached_limits) >= 1

    def test_assert_tradable_raises_when_halted(self) -> None:
        rm = RiskManager()
        rm.update_equity(D("2100000"))
        rm.update_equity(D("1500000"))
        with pytest.raises(KillSwitchEngaged):
            rm.assert_tradable()

    def test_peak_is_never_lowered_by_drawdown(self) -> None:
        rm = RiskManager()
        rm.update_equity(D("2100000"))
        rm.update_equity(D("1900000"))
        rm.update_equity(D("2200000"))
        assert rm.state.equity_peak == D("2200000")

    def test_reset_clears_switch(self) -> None:
        rm = RiskManager()
        rm.update_equity(D("2100000"))
        rm.update_equity(D("1500000"))
        assert rm.is_halted
        rm.reset(D("2100000"))
        assert not rm.is_halted


class TestPreTradeChecks:
    def test_oversized_position_rejected(self) -> None:
        rm = RiskManager()
        with pytest.raises(RiskLimitViolation, match="max single-name"):
            rm.check_order("TCS", D("0.20"), {}, {"TCS": "it"})

    def test_sector_cap_enforced(self) -> None:
        rm = RiskManager()
        weights = {f"IT{i}": D("0.06") for i in range(4)}
        sectors = {f"IT{i}": "it" for i in range(4)}
        with pytest.raises(RiskLimitViolation, match="sector"):
            rm.check_order("TCS", D("0.06"), weights, {**sectors, "TCS": "it"})

    def test_too_many_positions_rejected(self) -> None:
        rm = RiskManager()
        weights = {f"S{i}": D("0.02") for i in range(30)}
        sectors = {f"S{i}": f"s{i % 6}" for i in range(30)}
        with pytest.raises(RiskLimitViolation, match="max_positions"):
            rm.check_order("NEW", D("0.02"), weights, {**sectors, "NEW": "s1"})

    def test_cash_buffer_floor_enforced(self) -> None:
        rm = RiskManager()
        weights = {f"S{i}": D("0.07") for i in range(13)}
        sectors = {f"S{i}": f"s{i % 8}" for i in range(13)}
        with pytest.raises(RiskLimitViolation, match="cash buffer"):
            rm.check_order("NEW", D("0.05"), weights, {**sectors, "NEW": "s8"})

    def test_valid_order_passes(self) -> None:
        rm = RiskManager()
        rm.check_order("TCS", D("0.05"), {"INFY": D("0.05")},
                       {"TCS": "it", "INFY": "it"})

    def test_halted_manager_rejects_all_orders(self) -> None:
        rm = RiskManager()
        rm.update_equity(D("2100000"))
        rm.update_equity(D("1500000"))
        with pytest.raises(KillSwitchEngaged):
            rm.check_order("TCS", D("0.05"), {}, {"TCS": "it"})

    def test_per_trade_stop(self) -> None:
        rm = RiskManager()
        rm.check_stop(D("100"), D("93"))      # -7%, inside the 8% limit
        with pytest.raises(RiskLimitViolation, match="per-trade stop"):
            rm.check_stop(D("100"), D("91"))  # -9%

    def test_stop_rejects_bad_entry(self) -> None:
        with pytest.raises(ValueError):
            RiskManager().check_stop(D("0"), D("10"))


class TestPaperBroker:
    def test_buy_updates_cash_and_position(self) -> None:
        b = PaperBroker(capital=D("1000000"))
        b.set_quote(Quote("TCS", D("100")))
        r = b.place_market_order("TCS", D("100"), "BUY")
        assert r.status == "COMPLETE"
        assert len(b.get_positions()) == 1
        assert b.cash < D("1000000")

    def test_sell_reduces_position(self) -> None:
        b = PaperBroker(capital=D("1000000"))
        b.set_quote(Quote("TCS", D("100")))
        b.place_market_order("TCS", D("100"), "BUY")
        b.set_quote(Quote("TCS", D("120")))
        b.place_market_order("TCS", D("50"), "SELL")
        assert b.get_positions()[0].quantity == D("50")

    def test_cannot_short(self) -> None:
        """Long-only is a hard structural constraint, not a config option."""
        b = PaperBroker(capital=D("1000000"))
        b.set_quote(Quote("TCS", D("100")))
        r = b.place_market_order("TCS", D("10"), "SELL")
        assert r.status == "REJECTED"
        assert "long-only" in r.message

    def test_cannot_oversell(self) -> None:
        b = PaperBroker(capital=D("1000000"))
        b.set_quote(Quote("TCS", D("100")))
        b.place_market_order("TCS", D("10"), "BUY")
        r = b.place_market_order("TCS", D("999"), "SELL")
        assert r.status == "REJECTED"

    def test_insufficient_cash_rejected(self) -> None:
        b = PaperBroker(capital=D("10000"))
        b.set_quote(Quote("TCS", D("100")))
        r = b.place_market_order("TCS", D("1000"), "BUY")
        assert r.status == "REJECTED"
        assert "cash" in r.message

    def test_zero_quantity_rejected(self) -> None:
        b = PaperBroker()
        b.set_quote(Quote("TCS", D("100")))
        assert b.place_market_order("TCS", D("0"), "BUY").status == "REJECTED"

    def test_bad_side_rejected(self) -> None:
        with pytest.raises(ValueError, match="BUY or SELL"):
            PaperBroker().place_market_order("TCS", D("1"), "X")

    def test_account_value_includes_cash(self) -> None:
        """Regression: the engine once valued only positions, reporting a phantom
        -69% drawdown on a healthy partially-invested account."""
        b = PaperBroker(capital=D("1000000"))
        b.set_quote(Quote("TCS", D("100")))
        b.place_market_order("TCS", D("1000"), "BUY")
        # 1000 shares x 100 = 100k of stock, ~900k of cash. Total ~1,000,000 minus costs.
        assert b.account_value() > D("990000")
        assert b.account_value() < D("1000000")

    def test_costs_are_charged(self) -> None:
        b = PaperBroker(capital=D("1000000"))
        b.set_quote(Quote("TCS", D("100")))
        b.place_market_order("TCS", D("100"), "BUY")
        assert b.total_costs > 0

    def test_average_price_after_two_buys(self) -> None:
        b = PaperBroker(capital=D("1000000"))
        b.set_quote(Quote("TCS", D("100")))
        b.place_market_order("TCS", D("100"), "BUY")
        b.set_quote(Quote("TCS", D("200")))
        b.place_market_order("TCS", D("100"), "BUY")
        pos = b.get_positions()[0]
        assert pos.quantity == D("200")
        assert D("140") < pos.average_price < D("160")

    def test_reconcile_empty_for_paper(self) -> None:
        assert PaperBroker().reconcile() == []


class TestBrokerContract:
    def test_paper_implements_the_protocol(self) -> None:
        b = PaperBroker()
        for m in ("get_quote", "get_positions", "account_value",
                  "place_market_order", "cancel_all", "is_connected"):
            assert callable(getattr(b, m))

    def test_position_math(self) -> None:
        p = Position("TCS", D("10"), D("100"), D("120"))
        assert p.market_value == D("1200")
        assert p.unrealised_pnl == D("200")
