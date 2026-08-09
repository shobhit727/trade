"""Two-leg funding-carry driver: legs fill, funding settles, engine books trades."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

from cryptobot.backtest.carry import make_funding_provider, run_carry
from cryptobot.backtest.runner import generate_synthetic_ohlcv
from cryptobot.core.events import OrderSide
from cryptobot.strategies.funding_arb import FundingArbConfig, FundingArbStrategy


def _bars(seed: int = 5):
    start = datetime(2024, 1, 1, tzinfo=UTC)
    spot = generate_synthetic_ohlcv(start, n_bars=120, freq_minutes=60, seed=seed, drift=0.0)
    # perp = spot + decaying premium: +10bps on bar 1 -> -10bps by bar 121.
    # Forces entry at open, exit when the premium compresses below exit_bps.

    mult = [1.0 + 0.001 * (1.0 - i / 120.0) for i in range(120)]
    perp = []
    for b, m in zip(spot, mult):
        import dataclasses

        perp.append(dataclasses.replace(b, close=b.close * m, open=b.open * m, high=b.high * m, low=b.low * m))
    return spot, perp


def _carry(funding_rate: str):
    spot, perp = _bars()
    strat = FundingArbStrategy(
        FundingArbConfig(
            min_funding_rate=0.0,
            basis_entry_bps=0.0,
            basis_exit_bps=5.0,
            quantity=Decimal("1"),
        )
    )
    engine = asyncio.run(
        run_carry(
            spot,
            perp,
            strat,
            make_funding_provider(fixed_rate=funding_rate),
            initial_capital=10_000.0,
        )
    )
    return engine


def test_carry_legs_fill_and_exit():
    engine = _carry("0.001")
    trades = engine.get_trades()
    # entry (2 legs) + exit (2 legs) -> at least 4 fills on the book
    assert len(trades) >= 4


def test_carry_funding_is_charged():
    # Long spot / short perp, rate>0: short receives -> higher funding wins.
    hi = _carry("0.002")
    lo = _carry("0.0005")
    assert hi._portfolio.get_state().total_equity > lo._portfolio.get_state().total_equity


def test_carry_strategy_pair_direction():
    strat = FundingArbStrategy(FundingArbConfig(min_funding_rate=0.0, basis_entry_bps=0.0))
    sides = strat.feed(datetime(2024, 1, 1, tzinfo=UTC), Decimal("100"), Decimal("100.1"), Decimal("0.001"))
    assert sides == (OrderSide.SELL, OrderSide.BUY)
