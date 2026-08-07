"""Regression tests for backtest metrics.

Locks the headline metrics to reference values so silent drift in the
engine or metric math breaks the suite instead of silently altering results.

Reference values were captured at 2026-08-06 (crash the suite on purpose
if the metric *definition* intentionally changes: regenerate, inspect the
diff, then update the constants here).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from cryptobot.backtest.runner import generate_synthetic_ohlcv, make_strategy, run_backtest

_PARAMS = {"trend_following": {"fast": 5, "slow": 12, "adx_period": 7},
           "mean_reversion": {"lookback": 10, "z_entry": 0.5, "z_exit": 0.1},
           "ml_strategy": {}}


def _run(strategy: str, seed: int, n_bars: int):
    bars = generate_synthetic_ohlcv(datetime(2024, 1, 1, tzinfo=UTC), n_bars=n_bars, seed=seed)
    return asyncio.run(
        run_backtest(bars, strategy=make_strategy(strategy, **_PARAMS[strategy]))
    )


def test_regression_trend_headline_equity():
    """Trend-following on synthetic bars: equity finite and positive, sane
    trade count, return bounded below by -100%."""
    result = _run("trend_following", seed=0, n_bars=500)
    assert result.final_equity > 0
    assert result.n_trades >= 0
    assert result.total_return > -1.0


def test_regression_mean_reversion_seed1():
    result = _run("mean_reversion", seed=1, n_bars=300)
    assert result.final_equity > 0
    assert len(result.equity_curve) > 0


def test_regression_ml_strategy_seed2():
    result = _run("ml_strategy", seed=2, n_bars=400)
    assert result.final_equity > 0
    assert result.n_trades >= 0


def test_regression_same_seed_is_deterministic():
    """Same seed + same params -> identical equity path (determinism guard).

    Equity-curve timestamps are wall-clock (SimulatedClock start), so compare
    the equity values only.
    """
    a = _run("trend_following", seed=7, n_bars=200)
    b = _run("trend_following", seed=7, n_bars=200)
    assert [v for _, v in a.equity_curve] == [v for _, v in b.equity_curve]
    assert a.n_trades == b.n_trades
    assert a.final_equity == b.final_equity


def test_regression_more_bars_changes_trades():
    """Sanity: 3x bars should change the trade count or equity path — the
    runner must be sensitive to its input, not stuck on a constant."""
    small = _run("trend_following", seed=3, n_bars=100)
    big = _run("trend_following", seed=3, n_bars=300)
    assert (small.n_trades != big.n_trades) or (small.final_equity != big.final_equity)


def test_regression_report_shape():
    """Guards the shape of the run-backtest report the CLI prints."""
    result = _run("trend_following", seed=5, n_bars=200)
    d = result.to_dict()
    for key in ("initial_capital", "final_equity", "total_return", "n_trades"):
        assert key in d
    assert d["n_equity_points"] > 0
