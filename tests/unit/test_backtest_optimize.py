"""Tests for backtest/optimize.py (strategy parameter optimization)."""

from __future__ import annotations

from datetime import UTC, datetime

from cryptobot.backtest.optimize import (
    DEFAULT_PARAMS,
    OptimizationResult,
    ParamSpec,
    _coarse_grid,
    optimize_strategy,
)
from cryptobot.backtest.runner import generate_synthetic_ohlcv


def _bars():
    return generate_synthetic_ohlcv(
        start=datetime(2025, 1, 1, tzinfo=UTC),
        n_bars=500,
        freq_minutes=60,
        seed=1,
    )


def test_coarse_grid_int_float():
    params = [
        ParamSpec(name="a", low=1, high=5, kind="int"),
        ParamSpec(name="b", low=0.0, high=1.0),
    ]
    grid = _coarse_grid(params)
    assert len(grid) == 3 * 3
    for combo in grid:
        assert "a" in combo and "b" in combo


def test_coarse_grid_categorical():
    params = [ParamSpec(name="mode", low=0, high=0, kind="categorical", choices=["A", "B"])]
    grid = _coarse_grid(params)
    assert len(grid) == 2
    assert {c["mode"] for c in grid} == {"A", "B"}


def test_optimize_strategy_grid_fallback():
    bars = _bars()
    params = [
        ParamSpec(name="lookback", low=10, high=30, kind="int"),
        ParamSpec(name="z_entry", low=1.0, high=2.5),
    ]
    res = optimize_strategy(bars, params, n_trials=1, random_seed=7)
    assert isinstance(res, OptimizationResult)
    assert res.method == "grid"
    assert res.n_trials >= 1
    assert res.best_params
    assert res.best_score > -1e18


def test_optimize_strategy_returns_reasonable():
    bars = _bars()
    res = optimize_strategy(bars, DEFAULT_PARAMS[:2], n_trials=1, random_seed=3)
    assert res.best_score != float("inf")
    assert set(res.best_params).issubset({"lookback", "z_entry", "z_exit", "rsi_period"})


def test_optimize_requires_params():
    bars = _bars()
    try:
        optimize_strategy(bars, [], n_trials=1)
        assert False, "expected ValueError"
    except ValueError:
        pass
