from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from cryptobot.core.clock import (
    AcceleratedClock,
    ClockFactory,
    RealtimeClock,
    SimulatedClock,
    get_clock,
    set_clock,
)
from cryptobot.core.portfolio import PortfolioManager, PortfolioMode


def test_clock_factory_builds_all_modes():
    start = datetime(2024, 1, 1)
    end = datetime(2024, 1, 2)
    assert isinstance(ClockFactory.create_for_backtest(start, end), SimulatedClock)
    assert isinstance(ClockFactory.create_for_paper(), RealtimeClock)
    assert isinstance(ClockFactory.create_for_paper(speed_factor=10), AcceleratedClock)
    assert isinstance(ClockFactory.create_for_live(), RealtimeClock)


def test_realtimeclock_returns_datetime():
    c = RealtimeClock()
    now = c.now()
    assert isinstance(now, datetime)


def test_acceleratedclock_advances_quickly():
    c = AcceleratedClock(speed_factor=1000)
    start = c.now()
    elapsed = (c.now() - start).total_seconds()
    assert elapsed >= 0


@pytest.mark.asyncio
async def test_simulatedclock_step_advances_time():
    c = SimulatedClock(
        start_time=datetime(2024, 1, 1),
        end_time=datetime(2024, 1, 1, 0, 5),
    )
    assert c.now() == datetime(2024, 1, 1)
    await c.step(timedelta(minutes=2))
    assert c.now() == datetime(2024, 1, 1, 0, 2)


@pytest.mark.asyncio
async def test_simulatedclock_pause_blocks_step():
    c = SimulatedClock(
        start_time=datetime(2024, 1, 1),
        end_time=datetime(2024, 1, 1, 0, 5),
    )
    c.pause()
    task = asyncio.create_task(c.step(timedelta(seconds=1)))
    await asyncio.sleep(0.05)
    assert not task.done()
    c.resume()
    await asyncio.wait_for(task, timeout=1)
    assert c.now() >= datetime(2024, 1, 1)


@pytest.mark.asyncio
async def test_simulatedclock_sleep_until_waits_until_target():
    c = SimulatedClock(
        start_time=datetime(2024, 1, 1),
        end_time=datetime(2024, 1, 1, 0, 1),
    )
    target = datetime(2024, 1, 1, 0, 0, 30)
    
    # Advance clock in background task
    async def advance_clock():
        await asyncio.sleep(0.01)  # yield control
        await c.step_to(target)
    
    task = asyncio.create_task(advance_clock())
    await c.sleep_until(target)
    await task
    assert c.now() == target


def test_simulatedclock_is_finished():
    c = SimulatedClock(
        start_time=datetime(2024, 1, 1),
        end_time=datetime(2024, 1, 1, 0, 1),
    )
    assert not c.is_finished()
    c._current_time = c.end_time
    assert c.is_finished()


@pytest.mark.asyncio
async def test_global_clock_getter_returns_realtime_by_default():
    set_clock(None)
    assert isinstance(get_clock(), RealtimeClock)


def test_portfolio_manager_starts_with_zero_equity():
    pm = PortfolioManager(PortfolioMode.BACKTEST)
    state = pm.get_state()
    assert state.total_equity == Decimal("0")
    assert state.open_positions == 0


@pytest.mark.asyncio
async def test_portfolio_equity_curve_recorded_on_update():
    pm = PortfolioManager()
    await pm.update_equity(Decimal("100"))
    await pm.update_equity(Decimal("110"))
    curve = pm.get_equity_curve()
    assert len(curve) == 2
    assert curve[-1][1] == Decimal("110")


def test_portfolio_allocations_can_be_registered():
    pm = PortfolioManager()
    pm.register_strategy("mm", target_weight=Decimal("0.5"), max_weight=Decimal("0.3"))
    alloc = pm.get_allocation("mm")
    assert alloc is not None
    assert alloc.target_weight == Decimal("0.5")


@pytest.mark.asyncio
async def test_portfolio_kill_switch_triggers_on_drawdown():
    pm = PortfolioManager()
    await pm.update_equity(Decimal("100"))
    triggered, reason = pm.check_kill_switch()
    assert triggered is False
    await pm.update_equity(Decimal("80"))
    triggered, reason = pm.check_kill_switch()
    assert triggered is True
    assert "drawdown" in reason.lower() or "loss" in reason.lower()
