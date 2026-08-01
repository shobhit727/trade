from __future__ import annotations

import numpy as np
import numpy.typing as npt
from dataclasses import dataclass
from typing import Any, Optional, Literal
from enum import StrEnum

try:
    import quantile_forest as qf
    HAS_QRF = True
except ImportError:
    HAS_QRF = False

try:
    from sklearn.linear_model import QuantileRegressor
    HAS_SKLEARN_QR = True
except ImportError:
    HAS_SKLEARN_QR = False

from cryptobot.config import settings
from cryptobot.utils.logging import get_logger

logger = get_logger(__name__)


class VolatilityMethod(StrEnum):
    EWMA = "ewma"
    GARCH = "garch"
    REALIZED = "realized"
    QUANTILE = "quantile"
    NEURAL = "neural"


@dataclass
class VolatilityConfig:
    method: VolatilityMethod = VolatilityMethod.EWMA
    horizon: int = 5
    window: int = 20
    lambda_: float = 0.94
    garch_p: int = 1
    garch_q: int = 1
    quantiles: tuple[float, ...] = (0.05, 0.5, 0.95)
    n_estimators: int = 100
    max_depth: int = 5
    learning_rate: float = 0.1


class VolatilityModel:
    """
    Volatility forecasting model supporting multiple methods:
    - EWMA (Exponentially Weighted Moving Average)
    - GARCH (Generalized Autoregressive Conditional Heteroskedasticity)
    - Realized Volatility
    - Quantile Regression Forest (conditional quantiles)
    - Neural network (future)
    """

    name = "volatility"

    def __init__(self, config: VolatilityConfig | None = None):
        self.config = config or VolatilityConfig()
        self._fitted = False
        self._vol: Optional[float] = None
        self._model: Any = None
        self._returns: Optional[np.ndarray] = None
        self._conditional_quantiles: Optional[np.ndarray] = None

    def fit(self, returns: npt.NDArray[np.float64]) -> "VolatilityModel":
        """Fit volatility model on return series."""
        if returns.size < 2:
            self._fitted = False
            return self

        self._returns = returns.copy()

        if self.config.method == VolatilityMethod.EWMA:
            self._vol = self._ewma_variance(returns)
        elif self.config.method == VolatilityMethod.REALIZED:
            self._vol = float(np.var(returns, ddof=1))
        elif self.config.method == VolatilityMethod.GARCH:
            self._fit_garch(returns)
        elif self.config.method == VolatilityMethod.QUANTILE:
            self._fit_quantile(returns)
        else:
            # Default to EWMA
            self._vol = self._ewma_variance(returns)

        self._fitted = True
        return self

    def _ewma_variance(self, returns: npt.NDArray[np.float64]) -> float:
        """Compute EWMA variance."""
        lambda_ = self.config.lambda_
        var = float(returns[0] ** 2)
        for r in returns[1:]:
            var = lambda_ * var + (1 - lambda_) * (r ** 2)
        return var

    def _fit_garch(self, returns: npt.NDArray[np.float64]) -> None:
        """Fit GARCH(p, q) model using MLE approximation."""
        try:
            from arch import arch_model
            model = arch_model(
                returns * 100,  # Scale for numerical stability
                vol="Garch",
                p=self.config.garch_p,
                q=self.config.garch_q,
                dist="normal"
            )
            result = model.fit(disp="off", show_warning=False)
            self._model = result
            # Get conditional variance
            self._vol = float(result.conditional_volatility[-1] ** 2) / 10000
        except ImportError:
            logger.warning("arch package not installed, falling back to EWMA")
            self._vol = self._ewma_variance(self._returns)
        except Exception as e:
            logger.warning(f"GARCH fitting failed: {e}, falling back to EWMA")
            self._vol = self._ewma_variance(self._returns)

    def _fit_quantile(self, returns: npt.NDArray[np.float64]) -> None:
        """Fit quantile regression for conditional volatility quantiles."""
        n = len(returns)
        if n < self.config.window + 1:
            self._fitted = False
            return

        # Create lagged features
        X = self._create_lagged_features(returns, self.config.window)
        y = returns[self.config.window:]

        quantiles = self.config.quantiles
        self._conditional_quantiles = np.zeros((len(y), len(quantiles)))

        if HAS_QRF:
            self._fit_quantile_forest(X, y, quantiles)
        elif HAS_SKLEARN_QR:
            self._fit_sklearn_quantile(X, y, quantiles)
        else:
            # Simple rolling quantiles as fallback
            self._rolling_quantiles(returns, quantiles)

    def _create_lagged_features(
        self,
        returns: npt.NDArray[np.float64],
        window: int
    ) -> np.ndarray:
        """Create lagged features for quantile regression."""
        n = len(returns) - window
        X = np.zeros((n, window))
        for i in range(n):
            X[i] = returns[i:i+window]
        return X

    def _fit_quantile_forest(
        self,
        X: np.ndarray,
        y: np.ndarray,
        quantiles: tuple[float, ...]
    ) -> None:
        """Fit Quantile Regression Forest."""
        try:
            qrf = qf.RandomForestQuantileRegressor(
                n_estimators=self.config.n_estimators,
                max_depth=self.config.max_depth,
                random_state=42
            )
            qrf.fit(X, y)
            self._model = qrf
            self._conditional_quantiles = qrf.predict(X, quantiles=quantiles)
        except Exception as e:
            logger.warning(f"Quantile Forest failed: {e}")
            self._fallback_quantiles()

    def _fit_sklearn_quantile(
        self,
        X: np.ndarray,
        y: np.ndarray,
        quantiles: tuple[float, ...]
    ) -> None:
        """Fit sklearn QuantileRegressor for each quantile."""
        try:
            models = []
            for q in quantiles:
                qr = QuantileRegressor(
                    quantile=q,
                    alpha=0.0,
                    solver="highs"
                )
                qr.fit(X, y)
                models.append(qr)

            self._model = models
            preds = np.column_stack([m.predict(X) for m in models])
            self._conditional_quantiles = preds
        except Exception as e:
            logger.warning(f"Sklearn QuantileRegressor failed: {e}")
            self._fallback_quantiles()

    def _fallback_quantiles(self) -> None:
        """Fallback to rolling empirical quantiles."""
        if self._returns is None:
            return
        self._rolling_quantiles(self._returns, self.config.quantiles)

    def _rolling_quantiles(
        self,
        returns: npt.NDArray[np.float64],
        quantiles: tuple[float, ...]
    ) -> None:
        """Compute rolling empirical quantiles."""
        window = self.config.window
        n = len(returns)
        if n < window:
            return

        cond_quantiles = np.full((n, len(quantiles)), np.nan)
        for i in range(window, n):
            window_data = returns[i-window:i]
            for j, q in enumerate(quantiles):
                cond_quantiles[i, j] = np.quantile(window_data, q)
        self._conditional_quantiles = cond_quantiles

    def forecast(self, horizon: Optional[int] = None) -> float:
        """Forecast volatility for given horizon."""
        if not self._fitted or self._vol is None:
            return 0.0
        h = horizon or self.config.horizon
        return np.sqrt(self._vol * h)

    def forecast_series(
        self,
        returns: npt.NDArray[np.float64],
        horizon: Optional[int] = None
    ) -> np.ndarray:
        """Forecast rolling volatility."""
        if not self._fitted:
            self.fit(returns)

        h = horizon or self.config.horizon
        n = len(returns)
        forecasts = np.full(n, np.nan)

        window = self.config.window
        for i in range(max(self.config.window, 1), n):
            window_rets = returns[i-window:i]
            var = self._ewma_variance(window_rets)
            forecasts[i] = np.sqrt(var * (horizon or self.config.horizon))

        return forecasts

    def get_conditional_quantiles(
        self,
        returns: npt.NDArray[np.float64] | None = None
    ) -> Optional[np.ndarray]:
        """Get conditional quantile forecasts."""
        if self._conditional_quantiles is not None:
            return self._conditional_quantiles
        if returns is not None and len(returns) >= self.config.window:
            self.fit(returns)
            return self._conditional_quantiles
        return None

    def forecast_quantiles(
        self,
        returns: npt.NDArray[np.float64],
        horizon: int = 1,
        quantiles: Optional[tuple[float, ...]] = None
    ) -> np.ndarray:
        """Forecast conditional quantiles for future horizon."""
        if not self._fitted:
            self.fit(returns)

        q = quantiles or self.config.quantiles
        # Use last available conditional quantiles
        if self._conditional_quantiles is not None and len(self._conditional_quantiles) > 0:
            last_quantiles = self._conditional_quantiles[-1]
            # Scale by sqrt(horizon) for multi-step
            scale = np.sqrt(horizon)
            return last_quantiles * scale

        # Fallback: assume normal distribution
        vol = self.forecast(horizon)
        from scipy import stats
        return np.array([stats.norm.ppf(q) * vol for q in q])

    def summary(self) -> dict[str, Any]:
        return {
            "model": self.name,
            "method": self.config.method.value,
            "fitted": self._fitted,
            "horizon": self.config.horizon,
            "window": self.config.window,
            "current_vol": float(self._vol) if self._vol else 0.0,
            "current_vol_annualized": float(self._vol * 252) if self._vol else 0.0,
        }


def realized_volatility(
    returns: npt.NDArray[np.float64],
    window: int = 20
) -> np.ndarray:
    """Compute rolling realized volatility."""
    n = len(returns)
    rv = np.full(n, np.nan)
    for i in range(window, n):
        rv[i] = np.std(returns[i - window:i], ddof=1)
    return rv


def ewma_volatility(
    returns: npt.NDArray[np.float64],
    lambda_: float = 0.94
) -> np.ndarray:
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
    "VolatilityMethod",
    "realized_volatility",
    "ewma_volatility",
]