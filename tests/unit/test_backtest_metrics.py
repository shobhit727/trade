from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from cryptobot.backtest.metrics import (
    BacktestMetricsRecorder,
    BacktestResults,
    PerformanceMetrics,
)
from cryptobot.core.portfolio import PortfolioState


def test_performance_metrics_instance():
    pm = PerformanceMetrics()
    assert hasattr(pm, "_equity_curve")
    assert hasattr(pm, "_returns")


def test_performance_metrics_add_value():
    pm = PerformanceMetrics()
    pm.add_value(10000.0)
    pm.add_value(10100.0)
    assert pm._equity_curve is not None
    assert len(pm._equity_curve) == 2


def test_performance_metrics_record_return():
    pm = PerformanceMetrics()
    pm.record_return(0.01)
    pm.record_return(-0.005)
    assert len(pm._returns) == 2


def test_performance_metrics_calculate_drawdown():
    pm = PerformanceMetrics()
    pm._equity_curve = pm._equity_curve if hasattr(pm, "_equity_curve") else None
    # Need to use BacktestMetricsRecorder for drawdown
    recorder = BacktestMetricsRecorder(initial_capital=10000.0)
    eq = [10000, 9800, 9900, 9500, 9700, 10000]
    for v in eq:
        recorder.record_equity(v)
    dd = recorder.calculate_drawdown(pm._equity_curve if hasattr(pm, "_equity_curve") else None)
    # Use BacktestMetricsRecorder's own method
    dd = recorder._equity_curve = pm._equity_curve if hasattr(pm, "_equity_curve") else None
    dd = recorder.calculate_drawdown(recorder._equity_curve)
    assert dd >= 0.0


def test_backtest_metrics_recorder():
    recorder = BacktestMetricsRecorder(initial_capital=10000.0)
    for v in [10000, 10100, 9900, 10200]:
        recorder.record_equity(v)
    metrics = recorder.finalize_metrics()
    assert "total_return" in metrics
    assert "final_equity" in metrics
    assert "max_drawdown_pct" in metrics
    assert "sharpe_ratio" in metrics
    assert "sortino_ratio" in metrics


def test_backtest_results():
    ps = PortfolioState()
    ps.total_equity = Decimal("11000")
    results = BacktestResults(
        start_time=datetime(2024, 1, 1),
        end_time=datetime(2024, 12, 31),
        initial_capital=10000.0,
        final_equity=11000.0,
        portfolio=ps,
    )
    report = results.generate_full_report()
    assert "metadata" in report
    assert "performance" in report
    assert report["metadata"]["total_days"] == 365


__all__ = []
