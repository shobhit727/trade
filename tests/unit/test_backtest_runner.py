from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from cryptobot.backtest.runner import (
    OhlcvBar,
    generate_synthetic_ohlcv,
    make_strategy,
    run_backtest,
)
from cryptobot.execution.engine import ExecutionEngine
from cryptobot.execution.venue.simulated import SimulatedVenue


def _build_bars(n: int = 120, start_price: float = 100.0, vol: float = 0.005):
    start = datetime(2024, 1, 1)
    bars: list[OhlcvBar] = []
    price = start_price
    for i in range(n):
        ts = start + timedelta(minutes=i * 15)
        ret = -0.003 * (1 if i % 2 else -1)
        new_close = price * (1 + ret)
        bars.append(
            OhlcvBar(
                timestamp=ts,
                open=price,
                high=max(price, new_close) * 1.001,
                low=min(price, new_close) * 0.999,
                close=new_close,
                volume=100.0,
            )
        )
        price = new_close
    return bars


@pytest.mark.asyncio
async def test_generate_synthetic_ohlcv_runs_and_produces_bars():
    bars = generate_synthetic_ohlcv(datetime(2024, 1, 1), n_bars=50, freq_minutes=15, seed=1)
    assert len(bars) == 50
    assert all(b.high >= b.low for b in bars)
    assert all(b.close > 0 for b in bars)


@pytest.mark.asyncio
async def test_run_backtest_subsecond_freq_is_deterministic():
    start = datetime(2024, 1, 1)
    bars = generate_synthetic_ohlcv(start, n_bars=2000, freq_seconds=0.1, seed=9)
    deltas = [bars[i + 1].timestamp - bars[i].timestamp for i in range(3)]
    assert all(d == timedelta(milliseconds=100) for d in deltas)
    r1 = await run_backtest(bars, strategy=make_strategy("trend_following", fast=5, slow=12, adx_period=7), initial_capital=Decimal("10000"))
    r2 = await run_backtest(bars, strategy=make_strategy("trend_following", fast=5, slow=12, adx_period=7), initial_capital=Decimal("10000"))
    assert r1.final_equity == r2.final_equity
    assert r1.n_trades == r2.n_trades
    assert all(t["exit_time"].endswith("00") for t in r1.trades)


@pytest.mark.asyncio
async def test_run_backtest_mean_reversion_path_executes():
    strategy = make_strategy("mean_reversion", lookback=10, z_entry=0.5, z_exit=0.1)
    bars = _build_bars(n=120, vol=0.01)
    result = await run_backtest(bars, strategy=strategy, symbol="BTCUSDT", initial_capital=Decimal("10000"))
    assert result.initial_capital == Decimal("10000")
    assert result.final_equity >= Decimal("0")
    assert isinstance(result.total_return, float)
    assert result.n_trades >= 0
    assert isinstance(result.equity_curve, list)


@pytest.mark.asyncio
async def test_run_backtest_trend_following_with_passed_engine():
    strategy = make_strategy("trend_following", fast=5, slow=12, adx_period=7)
    venue = SimulatedVenue(slippage_bps=Decimal("3"), commission_bps=Decimal("5"))
    engine = ExecutionEngine(venue=venue)
    bars = generate_synthetic_ohlcv(datetime(2024, 1, 1), n_bars=80, vol=0.01, seed=7)
    result = await run_backtest(bars, strategy=strategy, initial_capital=Decimal("5000"), execution_engine=engine)
    assert result.n_trades >= 0
    assert result.initial_capital == Decimal("5000")


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy_name", ["one_shot", "trend_following"])
async def test_close_signal_executes_at_next_bar_open(strategy_name):
    from cryptobot.core.events import OrderEvent, OrderSide, OrderType

    class RecordingVenue(SimulatedVenue):
        def __init__(self):
            super().__init__(slippage_bps=Decimal("0"), commission_bps=Decimal("0"))
            self.submission_marks = []

        async def submit_order(self, order):
            self.submission_marks.append(self.prices[order.symbol])
            return await super().submit_order(order)

    class OneShotStrategy:
        name = strategy_name

        def __init__(self):
            self.sent = False

        def feed(self, symbol, *args, ts=None, **kwargs):
            if self.sent:
                return None
            self.sent = True
            return OrderEvent(
                symbol=symbol,
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                quantity=Decimal("1"),
                strategy=self.name,
            )

    bars = [
        OhlcvBar(datetime(2024, 1, 1) + timedelta(minutes=15 * i),
                 open=100 + i * 10, high=105 + i * 10,
                 low=95 + i * 10, close=102 + i * 10, volume=1000)
        for i in range(3)
    ]
    venue = RecordingVenue()
    engine = ExecutionEngine(venue=venue)

    await run_backtest(
        bars,
        strategy=OneShotStrategy(),
        symbol="BTCUSDT",
        initial_capital=Decimal("10000"),
        execution_engine=engine,
    )

    assert venue.submission_marks == [Decimal(str(bars[1].open))]


@pytest.mark.asyncio
async def test_run_backtest_rejects_empty_bars():
    strategy = make_strategy("mean_reversion")
    with pytest.raises(ValueError, match="no bars"):
        await run_backtest([], strategy=strategy, symbol="X")


def test_make_strategy_unknown_name_raises():
    with pytest.raises(ValueError):
        make_strategy("nope")


@pytest.mark.asyncio
async def test_run_backtest_total_return_equals_pct_change():
    strategy = make_strategy("mean_reversion", lookback=10, z_entry=1.5, z_exit=0.0, rsi_period=14)
    bars = _build_bars(n=80, vol=0.005)
    result = await run_backtest(bars, strategy=strategy, initial_capital=Decimal("1000"))
    expected = float((result.final_equity - result.initial_capital) / result.initial_capital)
    assert abs(result.total_return - expected) < 1e-9


def test_run_parallel_spreads_jobs_across_workers():
    from cryptobot.backtest.parallel import run_parallel

    jobs = [
        {"strategy": "trend_following", "params": {"fast": 5, "slow": 12}, "bars": 200},
        {"strategy": "mean_reversion", "params": {"lookback": 5}, "bars": 200},
        {"strategy": "trend_following", "params": {"fast": 8, "slow": 21}, "bars": 200},
    ]
    results = run_parallel(jobs, workers=2)
    assert len(results) == 3
    assert [r["index"] for r in results] == [0, 1, 2]
    assert all(r["n_trades"] >= 0 for r in results)
    assert results[0]["strategy"] == "trend_following"
    assert results[1]["strategy"] == "mean_reversion"


def test_run_parallel_empty_jobs_returns_empty():
    from cryptobot.backtest.parallel import run_parallel

    assert run_parallel([], workers=2) == []
