from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

from cryptobot.ml.models.direction import DirectionClassifier, DirectionConfig
from cryptobot.ml.models.regime import RegimeConfig, RegimeDetector
from cryptobot.ml.models.volatility import VolatilityConfig, VolatilityModel


@dataclass
class EnsembleConfig:
    models: list[str] | None = None  # "direction", "volatility", "regime"
    weights: list[float] | None = None
    direction_config: DirectionConfig | None = None
    volatility_config: VolatilityConfig | None = None
    regime_config: RegimeConfig | None = None
    meta_learner: str = "weighted_vote"  # weighted_vote, logistic_regression


class EnsembleModel:
    """
    Ensemble of ML models for robust predictions.

    Combines direction, volatility, and regime models with configurable
    aggregation methods (weighted voting, meta-learner).
    """

    name = "ensemble"

    def __init__(self, config: EnsembleConfig | None = None):
        self.config = config or EnsembleConfig()
        self.models: dict[str, Any] = {}
        self._fitted = False
        self._weights: np.ndarray | None = None

    def fit(self, features: npt.NDArray[np.float64], labels: npt.NDArray[np.float64]) -> EnsembleModel:
        """Fit all sub-models and meta-learner."""
        model_names = self.config.models or ["direction", "volatility", "regime"]
        weights = self.config.weights or [1.0] * len(model_names)
        self._weights = np.array(weights) / sum(weights)

        # Fit direction model
        if "direction" in model_names:
            dc = self.config.direction_config or DirectionConfig()
            self.models["direction"] = DirectionClassifier(dc).fit(features, labels)

        # Fit volatility model
        if "volatility" in model_names:
            vc = self.config.volatility_config or VolatilityConfig()
            returns = np.diff(labels.astype(float)) if len(labels) > 1 else np.zeros(len(labels))
            self.models["volatility"] = VolatilityModel(vc).fit(returns)

        # Fit regime model
        if "regime" in model_names:
            rc = self.config.regime_config or RegimeConfig()
            self.models["regime"] = RegimeDetector(rc).fit(features)

        self._fitted = True
        return self

    def predict_proba(self, features: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        """Get ensemble probability predictions."""
        if not self._fitted:
            self.fit(features, np.zeros(len(features)))

        n = len(features)
        probs = np.full((n, 2), 0.5)  # binary classification (issue #48)

        if "direction" in self.models:
            dir_probs = self.models["direction"].predict_proba(features)
            probs[:, 1] += self._weights[0] * dir_probs

        if "regime" in self.models:
            regime_probs = self.models["regime"].predict_proba(features)
            if regime_probs.shape[1] >= 2:
                probs[:, 1] += self._weights[-1] * regime_probs[:, 1]

        # Complete the binary distribution: column 0 was never populated, so
        # probabilities[:,0] stayed 0 and confidence was wrong below 0.5 (#48).
        probs[:, 0] = np.clip(1.0 - probs[:, 1], 0.0, 1.0)

        # Normalize
        row_sums = probs.sum(axis=1, keepdims=True)
        probs = probs / np.where(row_sums > 0, row_sums, 1)

        return probs

    def predict(self, features: npt.NDArray[np.float64]) -> npt.NDArray[np.int64]:
        """Predict class labels."""
        proba = self.predict_proba(features)
        return (proba[:, 1] > 0.5).astype(int)

    def predict_with_confidence(self, features: npt.NDArray[np.float64]) -> tuple[npt.NDArray[np.int64], npt.NDArray[np.float64]]:
        """Predict with confidence scores."""
        proba = self.predict_proba(features)
        preds = self.predict(features)
        confidence = np.max(proba, axis=1)
        return preds, confidence

    def predict_volatility(self, returns: npt.NDArray[np.float64], horizon: int = 5) -> float:
        """Predict volatility forecast."""
        if "volatility" in self.models:
            return self.models["volatility"].forecast(horizon)
        return 0.0

    def current_regime(self, features: npt.NDArray[np.float64]) -> int:
        """Get current market regime."""
        if "regime" in self.models:
            return self.models["regime"].current_regime(features)
        return 0

    def summary(self) -> dict[str, Any]:
        return {
            "model": self.name,
            "fitted": self._fitted,
            "sub_models": list(self.models.keys()),
            "weights": self._weights.tolist() if self._weights is not None else None,
            "meta_learner": self.config.meta_learner,
        }


def create_ensemble(
    direction_weight: float = 0.5,
    volatility_weight: float = 0.2,
    regime_weight: float = 0.3,
) -> EnsembleModel:
    """Create a standard ensemble with default weights."""
    config = EnsembleConfig(
        models=["direction", "volatility", "regime"],
        weights=[direction_weight, volatility_weight, regime_weight],
    )
    return EnsembleModel(config)


__all__ = [
    "EnsembleModel",
    "EnsembleConfig",
    "create_ensemble",
]
