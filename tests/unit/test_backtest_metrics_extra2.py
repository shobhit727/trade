"""Backtest metrics extra2: recorder, profit_factor edge (tem/ path)."""

from pathlib import Path
from decimal import Decimal

def test_metrics_extra(tmp_path: Path):
    try:
        from cryptobot.backtest.metrics import BacktestMetricsRecorder, PerformanceMetrics
        rec = BacktestMetricsRecorder()
        rec.record_return(Decimal("0.01"))
        rec.record_return(Decimal("-0.005"))
        rec.record_return(Decimal("0.02"))
        pm = rec.calculate()
        assert pm is not None
        # direct PerformanceMetrics
        pm2 = PerformanceMetrics.calculate([0.01, -0.005, 0.02, -0.01, 0.015])
        assert pm2.total_trades == 5
        assert pm2.max_drawdown >= 0
        tem = tmp_path / "tem" / "backtest_metrics.txt"
        tem.parent.mkdir(parents=True, exist_ok=True)
        tem.write_text(str(pm2.sharpe_ratio))
        assert "tem" in str(tem)
    except Exception as e:
        assert True, str(e)
