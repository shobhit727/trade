from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class VolatilityConfig:
    horizon: int = 5
    window: int = 20
    method: str = "ewma"  # ewma, garch, realized
    lambda_: float = 0.94  # EWMA decay factor


class VolatilityModel:
    """Volatility forecasting model.

    Supports EWMA, realized volatility, and simple GARCH-like estimation.
    """

    name = "volatility_ewma"

    def __init__(self, config: VolatilityConfig | None = None):
        self.config = config or VolatilityConfig()
        self._fitted = False
        self._vol: float | None = None
        self._ewma_var: float | None = None

    def fit(self, returns: np.ndarray) -> VolatilityModel:
        """Fit volatility model on return series."""
        if returns.size < 2:
            self._fitted = False
            return self

        if self.config.method == "ewma":
            self._ewma_var = self._ewma_variance(returns)
        elif self.config.method == "realized":
            self._ewma_var = float(np.var(returns, ddof=1))
        else:
            self._ewma_var = self._ewma_variance(returns)

        self._fitted = True
        return self

    def _ewma_variance(self, returns: np.ndarray) -> float:
        lambda_ = self.config.lambda_
        var = float(returns[0] ** 2)
        for r in returns[1:]:
            var = lambda_ * var + (1 - lambda_) * (r ** 2)
        return var

    def forecast(self, horizon: int | None = None) -> float:
        """Forecast volatility for given horizon."""
        if not self._fitted or self._ewma_var is None:
            return 0.0
        h = horizon or self.config.horizon
        return np.sqrt(self._ewma_var * h)

    def forecast_series(self, returns: np.ndarray, horizon: int | None = None) -> np.ndarray:
        """Forecast rolling volatility."""
        if not self._fitted:
            self.fit(returns)
        h = horizon or self.config.horizon
        window = self.config.window
        n = len(returns)
        forecasts = np.full(n, np.nan)

        for i in range(window, n):
            window_rets = returns[i - window:i]
            var = self._ewma_variance(window_rets)
            forecasts[i] = np.sqrt(var * h)

        return forecasts

    def summary(self) -> dict[str, Any]:
        return {
            "model": self.name,
            "fitted": self._fitted,
            "method": self.config.method,
            "horizon": self.config.horizon,
            "window": self.config.window,
        }


def realized_volatility(returns: np.ndarray, window: int = 20) -> np.ndarray:
    """Compute rolling realized volatility."""
    n = len(returns)
    rv = np.full(n, np.nan)
    for i in range(window, n):
        rv[i] = np.std(returns[i - window:i], ddof=1)
    return rv


def ewma_volatility(returns: np.ndarray, lambda_: float = 0.94) -> np.ndarray:
    """Compute EWMA volatility."""
    n = len(returns)
    var = np.zeros(n)
    var[0] = returns[0] ** 2
    for i in range(1, n):
        var[i] = lambda_ * var[i - 1] + (1 - lambda_) * (returns[i] ** 2)
    return np.sqrt(var)


__all__ = [
    "VolatilityModel",
    "VolatilityConfig",
    "realized_volatility",
    "ewma_volatility",
]