from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from cryptobot.ml.models.direction import DirectionClassifier, DirectionConfig
from cryptobot.ml.models.volatility import VolatilityModel, VolatilityConfig
from cryptobot.ml.models.regime import RegimeDetector, RegimeConfig


@dataclass
class EnsembleConfig:
    models: list[str] | None = None  # "direction", "volatility", "regime"
    weights: list[float] | None = None
    direction_config: DirectionConfig | None = None
    volatility_config: VolatilityConfig | None = None
    regime_config: RegimeConfig | None = None
    meta_learner: str = "weighted_vote"  # weighted_vote, logistic_regression


class EnsembleModel:
    """Ensemble of ML models for robust predictions.

    Combines direction, volatility, and regime models with configurable
    aggregation methods (weighted voting, meta-learner).
    """

    name = "ensemble"

    def __init__(self, config: EnsembleConfig | None = None):
        self.config = config or EnsembleConfig()
        self.models = {}
        self._fitted = False
        self._weights = None

    def fit(self, features: np.ndarray, labels: np.ndarray) -> EnsembleModel:
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

    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        """Get ensemble probability predictions."""
        if not self._fitted:
            self.fit(features, np.zeros(len(features)))

        n = len(features)
        probs = np.zeros((n, 2))  # binary classification

        if "direction" in self.models:
            dir_probs = self.models["direction"].predict_proba(features)
            probs[:, 1] += self._weights[0] * dir_probs

        if "regime" in self.models:
            regime_probs = self.models["regime"].predict_proba(features)
            if regime_probs.shape[1] >= 2:
                probs[:, 1] += self._weights[-1] * regime_probs[:, 1]

        # Normalize
        probs = probs / probs.sum(axis=1, keepdims=True)
        return probs

    def predict(self, features: np.ndarray) -> np.ndarray:
        """Predict class labels."""
        proba = self.predict_proba(features)
        return (proba[:, 1] > 0.5).astype(int)

    def predict_with_confidence(self, features: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Predict with confidence scores."""
        proba = self.predict_proba(features)
        preds = self.predict(features)
        confidence = np.max(proba, axis=1)
        return preds, confidence

    def predict_volatility(self, returns: np.ndarray, horizon: int = 5) -> float:
        """Predict volatility forecast."""
        if "volatility" in self.models:
            return self.models["volatility"].forecast(horizon)
        return 0.0

    def current_regime(self, features: np.ndarray) -> int:
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