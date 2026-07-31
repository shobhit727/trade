from __future__ import annotations

import logging
from datetime import datetime
from math import sqrt
from typing import Any

import numpy as np
import pandas as pd

from cryptobot.core.portfolio import PortfolioState

# We rely on the portfolio state for current PnL and equity calculation.
# The metrics themselves focus on time-series analysis of performance over multiple runs/periods.


class PerformanceMetrics:
    """
    A container class to calculate, aggregate, and report key financial performance indicators (KPIs).
    These metrics are critical for backtesting validation against industry standards defined in plan.md.
    """
    def __init__(self):
        # Store historical data points that contribute to the final scores
        self._equity_curve: pd.Series | None = None # Daily/Interval-based equity value
        self._returns: list[float] = []               # Log returns or simple percentage changes
        self._drawdown_series: list[float] = []

    def add_value(self, value: float):
        """Adds a new data point (e.g., daily total equity value) to the curve."""
        if self._equity_curve is None:
            self._equity_curve = pd.Series([], dtype=float)
        self._equity_curve = pd.concat([self._equity_curve, pd.Series([value])]).reset_index(drop=True)

    def record_return(self, ret: float):
        """Records a return percentage for calculating statistics."""
        self._returns.append(ret)

    def calculate_drawdown(self, equity_curve: pd.Series) -> float:
        """Calculates the Maximum Drawdown (MaxDD) of the entire run."""
        if equity_curve is None or equity_curve.empty:
            return 0.0
        peak = equity_curve.cummax()
        peak = peak.replace(0, np.nan)
        drawdown = (peak - equity_curve) / peak
        return float(drawdown.fillna(0).max() * 100)

    def calculate_sharpe_ratio(self, returns: list[float], risk_free_rate: float = 0.02) -> float:
        """
        Calculates the annualized Sharpe Ratio.
        Assumes returns are measured over a period (e.g., log returns).
        Requires proper scaling factor based on observation frequency.
        """
        if not returns:
            return 0.0

        # Calculate mean and standard deviation of observed returns
        mean_return = np.mean(returns)
        std_dev = np.std(returns)

        # Annualization factors (assuming daily data for simplicity, adjust as needed)
        annualization_factor = 252 # Trading days per year
        if std_dev == 0:
            return 0.0

        sharpe = (mean_return * annualization_factor - risk_free_rate) / (std_dev * sqrt(annualization_factor))
        return sharpe

    def calculate_sortino_ratio(self, returns: list[float], target_rate: float = 0.02) -> float:
        """Calculates the annualized Sortino Ratio (focusing only on downside risk)."""
        if not returns:
            return 0.0

        # Calculate negative returns relative to a minimum acceptable rate
        downside_returns = [r for r in returns if r < target_rate]
        if not downside_returns:
            return float('inf') # Perfect performance regarding downside risk

        np.mean(downside_returns)
        std_downside = np.std(downside_returns)

        # Annualization
        annualization_factor = 252
        if std_downside == 0:
            return float('inf')

        sortino = (np.mean(returns) * annualization_factor - target_rate) / (std_downside * sqrt(annualization_factor))
        return sortino


class BacktestMetricsRecorder:
    """
    A dedicated helper class to calculate and aggregate all required performance metrics
    after a full backtest run is complete.
    """
    def __init__(self, initial_capital: float):
        self._initial_capital = initial_capital
        self._equity_history: list[float] = [] # History of total equity values

    def record_equity(self, value: float):
        """Records a new total equity value."""
        self._equity_history.append(value)

    def finalize_metrics(self) -> dict[str, Any]:
        """Calculates all metrics based on the recorded history."""
        if not self._equity_history:
            return {"error": "No data points recorded."}

        # 1. Calculate Equity Curve and Drawdown
        self._equity_curve = pd.Series(self._equity_history)
        max_drawdown_pct = self.calculate_drawdown(self._equity_curve)

        # 2. Calculate Returns (Assuming simple log return calculation for robust stats)
        returns = []
        prev_value = self._initial_capital
        for current_value in self._equity_history:
            if prev_value > 0:
                ret = (current_value - prev_value) / prev_value # Percentage change from last step
                returns.append(ret)
            prev_value = current_value

        # 3. Calculate Advanced Ratios
        sharpe = self.calculate_sharpe_ratio(returns)
        sortino = self.calculate_sortino_ratio(returns)

        return {
            "total_return": (self._equity_history[-1] / self._initial_capital - 1) * 100,
            "final_equity": self._equity_history[-1],
            "max_drawdown_pct": max_drawdown_pct, # MaxDD (%)
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "total_periods": len(self._equity_history) - 1,
        }

    def calculate_drawdown(self, equity_curve: pd.Series) -> float:
        """Calculates the Maximum Drawdown (MaxDD) of the entire run."""
        if equity_curve is None or equity_curve.empty:
            return 0.0
        peak = equity_curve.cummax()
        peak = peak.replace(0, np.nan)
        drawdown = (peak - equity_curve) / peak
        return float(drawdown.fillna(0).max() * 100)

    def calculate_sharpe_ratio(self, returns: list[float], risk_free_rate: float = 0.02) -> float:
        """Calculates the annualized Sharpe Ratio."""
        if not returns:
            return 0.0

        # We use numpy functions for better numerical stability
        np.mean(returns)
        std_dev = np.std(returns)

        annualization_factor = 252  # Assuming daily/high frequency data sampled over years
        if std_dev == 0:
            return 0.0

        sharpe = (np.mean([r * annualization_factor for r in returns]) - risk_free_rate) / (std_dev * sqrt(annualization_factor))
        return sharpe

    def calculate_sortino_ratio(self, returns: list[float], target_rate: float = 0.02) -> float:
        if not returns:
            return 0.0
        downside = [r for r in returns if r < target_rate]
        if not downside:
            return 0.0
        downside_std = np.std(downside)
        if downside_std == 0:
            return 0.0
        annualization_factor = 252
        return float((np.mean(returns) * annualization_factor - target_rate) / (downside_std * sqrt(annualization_factor)))


# --- Updated BacktestResults Structure (for better separation of concerns) ---
class BacktestResults:
    """Container for the outcome metrics and portfolio state of a backtest run."""
    def __init__(self, start_time: datetime, end_time: datetime, initial_capital: float, final_equity: float, portfolio: PortfolioState):
        self.start_time = start_time
        self.end_time = end_time
        self.initial_capital = initial_capital
        self.final_equity = final_equity
        self.portfolio = portfolio

    def generate_full_report(self) -> dict[str, Any]:
        """Aggregates all required performance metrics into one object."""
        recorder = BacktestMetricsRecorder(initial_capital=self.initial_capital)
        # Simulate populating the recorder from the final portfolio state's journey (needs implementation)
        # For now, we fake an equity curve based on PnL delta for demonstration:
        mock_equity_history = [self.initial_capital]
        current_eq = self.initial_capital

        # Simple simulation of PnL effect over time to generate a history
        # This is placeholder and must be replaced by actual state saving/reading logic in reality
        temp_mock_pnl_delta = (self.final_equity - self.initial_capital) * 0.1 # Assume some small movement for diversity
        for i in range(2, 5): # Simulate a few steps
            current_eq += temp_mock_pnl_delta * (i / 3)
            mock_equity_history.append(current_eq)

        recorder._equity_history = mock_equity_history[1:]

        metrics = recorder.finalize_metrics()
        return {
            "metadata": {
                "start": self.start_time,
                "end": self.end_time,
                "total_days": (self.end_time - self.start_time).days
            },
            "performance": metrics,
            "final_portfolio_snapshot": self.portfolio.__dict__ # For audit/debugging
        }


if __name__ == '__main__':
    import logging

    logging.warning("Execution blocked for standalone testing. Requires setup of core dependencies.")
