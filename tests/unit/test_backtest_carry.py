"""Two-leg funding-carry driver: legs fill, funding settles, engine books trades."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from cryptobot.backtest.carry import (
    align_spot_to_perp,
    make_funding_provider,
    run_carry,
)
from cryptobot.backtest.runner import OhlcvBar, generate_synthetic_ohlcv
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


def test_carry_equity_scaled_sizing():
    strat = FundingArbStrategy(
        FundingArbConfig(min_funding_rate=0.0, basis_entry_bps=0.0, risk_fraction=Decimal("0.01"))
    )
    # 1% of 10_000 equity at spot 100 -> 1.0 per leg.
    assert strat.size_position(Decimal("100"), Decimal("10000")) == Decimal("1.00000000")
    # Capped notional kicks in.
    capped = FundingArbStrategy(
        FundingArbConfig(
            min_funding_rate=0.0,
            basis_entry_bps=0.0,
            risk_fraction=Decimal("0.5"),
            max_notional=Decimal("500"),
        )
    )
    assert capped.size_position(Decimal("100"), Decimal("10000")) == Decimal("5.00000000")
    # No risk_fraction -> fixed quantity from config.
    fixed = FundingArbStrategy(FundingArbConfig(quantity=Decimal("2")))
    assert fixed.size_position(Decimal("100"), Decimal("10000")) == Decimal("2")


def test_carry_risk_scaled_run_sizes_trades():
    spot, perp = _bars()
    strat = FundingArbStrategy(
        FundingArbConfig(
            min_funding_rate=0.0,
            basis_entry_bps=0.0,
            basis_exit_bps=5.0,
            quantity=Decimal("1"),
            risk_fraction=Decimal("0.01"),
        )
    )
    engine = asyncio.run(
        run_carry(
            spot,
            perp,
            strat,
            make_funding_provider(fixed_rate="0.001"),
            initial_capital=10_000.0,
        )
    )
    trades = engine.get_trades()
    assert len(trades) >= 4
    # 1% of 10k equity on a ~100-price pair -> ~1 unit per leg, not the 10k/100
    # fixed fallback (100 units).
    perp_entries = [t for t in trades if t.symbol.endswith("PERP")]
    assert perp_entries, "expected perp legs in trades"
    assert all(t.quantity <= Decimal("1.5") for t in perp_entries), [t.quantity for t in perp_entries]


def test_align_spot_to_perp_matches_close_instants():
    t0 = datetime(2024, 1, 1, tzinfo=UTC)
    # Perp bars open on the 8h grid (U); a bar at U closes at U+8h.
    perp = [OhlcvBar(timestamp=t0 + timedelta(hours=8 * i), open=100.0, high=100.0, low=100.0, close=101.0, volume=10.0) for i in range(3)]
    # Spot 1h bars; the bar opening at U+7h closes at U+8h == perp close instant.
    spot = [OhlcvBar(timestamp=t0 + timedelta(hours=7 + 8 * i), open=1.0, high=1.0, low=1.0, close=float(100 + i), volume=1.0) for i in range(3)]
    aligned = align_spot_to_perp(spot, perp)
    assert len(aligned) == 3
    # Each aligned bar carries the perp timestamp (settlement grid preserved) and
    # the spot close sampled at the perp close instant.
    for b, i in zip(aligned, range(3)):
        assert b.timestamp == perp[i].timestamp
        assert b.close == float(100 + i)
    # Off-grid spot bars (any hour other than U+7h) pair with nothing.
    shifted = [OhlcvBar(timestamp=t0 + timedelta(hours=8 + 8 * i), open=1.0, high=1.0, low=1.0, close=float(100 + i), volume=1.0) for i in range(3)]
    assert align_spot_to_perp(shifted, perp) == []
