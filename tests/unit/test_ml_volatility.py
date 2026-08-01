"""Tests for cryptobot.ml.models.volatility"""

import numpy as np

from cryptobot.ml.models.volatility import (
    VolatilityConfig,
    VolatilityModel,
    ewma_volatility,
    realized_volatility,
)


def test_volatility_ewma_fit_and_forecast():
    returns = np.random.normal(0, 0.02, 100)
    model = VolatilityModel(VolatilityConfig(method="ewma"))
    model.fit(returns)
    assert model._fitted
    forecast = model.forecast(horizon=5)
    assert forecast > 0


def test_volatility_realized_method():
    returns = np.random.normal(0, 0.02, 100)
    model = VolatilityModel(VolatilityConfig(method="realized"))
    model.fit(returns)
    forecast = model.forecast()
    assert forecast > 0


def test_volatility_forecast_series():
    returns = np.random.normal(0, 0.02, 100)
    model = VolatilityModel(VolatilityConfig(window=20))
    model.fit(returns)
    forecasts = model.forecast_series(returns)
    assert len(forecasts) == len(returns)
    assert not np.all(np.isnan(forecasts))


def test_realized_volatility_function():
    returns = np.random.normal(0, 0.02, 100)
    rv = realized_volatility(returns, window=20)
    assert len(rv) == len(returns)
    assert not np.all(np.isnan(rv))


def test_ewma_volatility_function():
    returns = np.random.normal(0, 0.02, 100)
    ewma_vol = ewma_volatility(returns, lambda_=0.94)
    assert len(ewma_vol) == len(returns)
    assert not np.all(np.isnan(ewma_vol))


def test_volatility_model_summary():
    model = VolatilityModel(VolatilityConfig(method="ewma"))
    model.fit(np.random.normal(0, 0.02, 100))
    summary = model.summary()
    assert summary["model"] == "volatility_ewma"
    assert summary["fitted"] is True
    assert "method" in summary
