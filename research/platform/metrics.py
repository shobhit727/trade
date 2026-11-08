"""Portfolio performance metrics with an explicit sampling-frequency contract."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Sequence

import numpy as np
import pandas as pd


@dataclass(frozen=True, slots=True)
class PortfolioMetrics:
    """Risk/return metrics derived from one market-scoped equity curve."""

    observations: int
    total_return: float
    cagr: float
    volatility: float
    sharpe: float
    sortino: float
    max_drawdown: float
    calmar: float
    win_rate: float
    average_period_return: float
    best_period_return: float
    worst_period_return: float
    periods_per_year: int
    annual_risk_free_rate: float

    def to_dict(self) -> dict[str, float | int]:
        # Keep output JSON-ready and avoid mixing Decimal or NumPy scalar objects.
        return asdict(self)


def compute_portfolio_metrics(
    equity_curve: pd.Series | Sequence[float],
    *,
    periods_per_year: int,
    annual_risk_free_rate: float = 0.0,
) -> PortfolioMetrics:
    """Compute performance metrics from a positive equity series.

    The caller must choose the correct annualisation frequency for the dataset:
    for example 252 for NSE daily bars, 365 for calendar-day crypto series, or a
    resolution-specific rate. This function does not infer frequency from timestamps.
    Returns are computed from consecutive equity observations; no missing rows are filled.
    """
    # Validate sampling and return assumptions before performing financial calculations.
    if periods_per_year < 1:
        raise ValueError("periods_per_year must be supplied and positive")
    if not np.isfinite(annual_risk_free_rate) or annual_risk_free_rate <= -1:
        raise ValueError("annual_risk_free_rate must be finite and greater than -100 percent")
    if isinstance(equity_curve, pd.Series):
        if isinstance(equity_curve.index, pd.DatetimeIndex):
            if equity_curve.index.tz is None or not equity_curve.index.is_monotonic_increasing:
                raise ValueError("datetime equity index must be timezone-aware and increasing")
            if equity_curve.index.has_duplicates:
                raise ValueError("equity timestamps must be unique")
        raw_values = equity_curve.to_numpy()
    else:
        raw_values = np.asarray(equity_curve)
    values = np.asarray([float(value) for value in raw_values], dtype=np.float64)
    if values.ndim != 1 or len(values) < 2:
        raise ValueError("equity_curve must contain at least two observations")
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError("equity values must be finite and positive")

    # Periodic returns derive only from the supplied equity history.
    returns = values[1:] / values[:-1] - 1.0
    observations = len(returns)
    years = observations / periods_per_year
    total_return = float(values[-1] / values[0] - 1.0)
    cagr = float((values[-1] / values[0]) ** (1.0 / years) - 1.0) if years > 0 else 0.0
    volatility = (
        float(np.std(returns, ddof=1) * np.sqrt(periods_per_year))
        if observations > 1 else 0.0
    )
    risk_free_period = (1.0 + annual_risk_free_rate) ** (1.0 / periods_per_year) - 1.0
    excess = returns - risk_free_period
    excess_std = float(np.std(excess, ddof=1)) if observations > 1 else 0.0
    sharpe = (
        float(np.mean(excess) / excess_std * np.sqrt(periods_per_year))
        if excess_std > 0 else 0.0
    )
    downside = np.minimum(excess, 0.0)
    downside_deviation = float(np.sqrt(np.mean(np.square(downside))))
    sortino = (
        float(np.mean(excess) / downside_deviation * np.sqrt(periods_per_year))
        if downside_deviation > 0 else 0.0
    )

    # Include the initial equity point when computing the high-water mark.
    peaks = np.maximum.accumulate(values)
    drawdowns = values / peaks - 1.0
    max_drawdown = float(np.min(drawdowns))
    calmar = float(cagr / abs(max_drawdown)) if max_drawdown < 0 else 0.0

    return PortfolioMetrics(
        observations=observations,
        total_return=total_return,
        cagr=cagr,
        volatility=volatility,
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown=max_drawdown,
        calmar=calmar,
        win_rate=float(np.mean(returns > 0)),
        average_period_return=float(np.mean(returns)),
        best_period_return=float(np.max(returns)),
        worst_period_return=float(np.min(returns)),
        periods_per_year=periods_per_year,
        annual_risk_free_rate=float(annual_risk_free_rate),
    )
