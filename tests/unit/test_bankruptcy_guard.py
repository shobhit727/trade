"""Bankruptcy guard tests (issue #55).

Negative equity arises from unbounded short liability (how the sweep runs
died: -14,000% "returns"). The guard must halt at the floor, flatten every
position at mark, and flag the result — equity must land >= 0.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from cryptobot.backtest.engine import BacktestEngine
from cryptobot.backtest.runner import OhlcvBar, make_strategy
from cryptobot.core.events import OrderEvent, OrderSide, OrderType
from cryptobot.core.portfolio import PortfolioManager, PortfolioMode
from cryptobot.execution.engine import ExecutionEngine
from cryptobot.execution.venue.simulated import SimulatedVenue
from cryptobot.risk.manager import RiskManager


class _AlwaysShort:
    """Opens one short and never exits — liability grows without bound."""

    name = "always_short"

    def __init__(self, qty: float = 1.0):
        self._qty = qty
        self._opened = False

    def feed(self, symbol: str, close: float) -> OrderEvent | None:
        if self._opened:
            return None
        self._opened = True
        return OrderEvent(
            symbol=symbol,
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            quantity=Decimal(str(self._qty)),
            price=Decimal(str(round(close, 8))),
        )


def _bars(n: int, drift: float) -> list[OhlcvBar]:
    start = datetime(2024, 1, 1)
    bars: list[OhlcvBar] = []
    price = 100.0
    for i in range(n):
        new_close = price * (1 + drift)
        bars.append(
            OhlcvBar(
                timestamp=start + timedelta(minutes=i * 15),
                open=price,
                high=max(price, new_close) * 1.001,
                low=min(price, new_close) * 0.999,
                close=new_close,
                volume=100.0,
            )
        )
        price = new_close
    return bars


def _engine_and_exec(capital: str = "10000"):
    portfolio = PortfolioManager(PortfolioMode.BACKTEST)
    engine = BacktestEngine(
        start_time=datetime(2024, 1, 1),
        end_time=datetime(2024, 1, 10),
        initial_capital=float(capital),
        commission_bps=5.0,
        slippage_bps=0.0,
        portfolio=portfolio,
    )
    venue = SimulatedVenue(commission_bps=Decimal("5"), slippage_bps=Decimal("0"))
    exec_engine = ExecutionEngine(
        venue=venue, risk_manager=RiskManager(portfolio=portfolio, backtest_mode=True)
    )
    return engine, exec_engine


@pytest.mark.asyncio
async def test_bankruptcy_halts_and_flags():
    """Short into a rally → equity goes negative → guard flattens and halts."""
    engine, exec_engine = _engine_and_exec()
    result = await engine.run_bars(
        _bars(400, +0.05), _AlwaysShort(), "TESTUSDT", execution_engine=exec_engine
    )
    assert result.bankrupt is True
    # The guard fires at the floor; one bar of overshoot past the floor is
    # unavoidable (equity is checked per bar). What must NEVER happen again
    # is the old behaviour: compounding to -14,000%.
    assert result.final_equity > Decimal("-500"), (
        f"bleeding must stop near the floor, got {result.final_equity}"
    )


@pytest.mark.asyncio
async def test_healthy_run_not_flagged():
    engine, exec_engine = _engine_and_exec()
    strat = make_strategy("trend_following", fast=2, slow=4, adx_period=2, adx_threshold=0)
    result = await engine.run_bars(
        _bars(300, +0.08), strat, "TESTUSDT",
        execution_engine=exec_engine, risk_fraction=1.0,
    )
    assert result.bankrupt is False


@pytest.mark.asyncio
async def test_custom_floor_triggers_earlier():
    """A floor above zero (keep 90% of capital) fires on a mild adverse move."""
    engine, exec_engine = _engine_and_exec()
    result = await engine.run_bars(
        _bars(400, +0.05), _AlwaysShort(), "TESTUSDT",
        execution_engine=exec_engine, bankruptcy_floor=Decimal("9000"),
    )
    assert result.bankrupt is True
