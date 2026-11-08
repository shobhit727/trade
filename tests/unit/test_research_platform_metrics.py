"""Tests for portfolio metrics and explicit sampling-frequency annualisation."""


import numpy as np
import pandas as pd
import pytest

from research.platform.metrics import compute_portfolio_metrics


def test_portfolio_metrics_use_explicit_periods_per_year() -> None:
    # The same equity history annualises differently under different exchange calendars.
    dates = pd.date_range("2025-01-01", periods=6, freq="D", tz="UTC")
    equity = pd.Series([100.0, 101.0, 99.0, 102.0, 103.0, 104.0], index=dates)
    nse = compute_portfolio_metrics(equity, periods_per_year=252)
    crypto = compute_portfolio_metrics(equity, periods_per_year=365)
    assert nse.observations == 5
    assert nse.total_return == pytest.approx(0.04)
    assert nse.cagr != crypto.cagr
    assert -1.0 <= nse.max_drawdown <= 0.0
    assert 0.0 <= nse.win_rate <= 1.0


def test_portfolio_metrics_reject_missing_frequency_and_invalid_equity() -> None:
    # Frequency and capital validity must be supplied rather than inferred.
    with pytest.raises(ValueError, match="periods_per_year"):
        compute_portfolio_metrics([100.0, 101.0], periods_per_year=0)
    with pytest.raises(ValueError, match="positive"):
        compute_portfolio_metrics([100.0, 0.0], periods_per_year=252)
    with pytest.raises(ValueError, match="at least two"):
        compute_portfolio_metrics([100.0], periods_per_year=252)
    with pytest.raises(ValueError, match="timezone-aware"):
        compute_portfolio_metrics(
            pd.Series([100.0, 101.0], index=pd.date_range("2025-01-01", periods=2)),
            periods_per_year=252,
        )
