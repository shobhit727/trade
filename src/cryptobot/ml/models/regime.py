from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class RegimeConfig:
    n_regimes: int = 3
    window: int = 50
    method: str = "hmm"  # hmm, kmeans, threshold
    min_duration: int = 5  # minimum bars per regime


class RegimeDetector:
    """Market regime detection.

    Identifies market regimes (trend, mean-reversion, high-vol, low-vol, etc.)
    using HMM-like clustering or threshold-based rules.
    """

    name = "regime_detector"

    def __init__(self, config: RegimeConfig | None = None):
        self.config = config or RegimeConfig()
        self._fitted = False
        self._regime_labels: np.ndarray | None = None
        self._regime_stats: dict[int, dict[str, float]] = {}

    def fit(self, features: np.ndarray) -> RegimeDetector:
        """Fit regime detector on feature matrix.

        Args:
            features: (n_samples, n_features) array
        """
        n = features.shape[0]
        if n < self.config.window:
            self._fitted = False
            return self

        if self.config.method == "kmeans":
            self._regime_labels = self._kmeans_regimes(features)
        elif self.config.method == "threshold":
            self._regime_labels = self._threshold_regimes(features)
        else:
            self._regime_labels = self._kmeans_regimes(features)

        self._compute_regime_stats(features)
        self._fitted = True
        return self

    def _kmeans_regimes(self, features: np.ndarray) -> np.ndarray:
        """Simple k-means clustering for regimes."""
        n = features.shape[0]
        k = self.config.n_regimes

        # Use first 2 principal components or first 2 features
        if features.shape[1] >= 2:
            X = features[:, :2]
        else:
            X = features

        # Simple k-means
        rng = np.random.default_rng(42)
        centroids = X[rng.choice(n, k, replace=False)]

        for _ in range(100):
            distances = np.sum((X[:, np.newaxis] - centroids) ** 2, axis=2)
            labels = np.argmin(distances, axis=1)
            new_centroids = np.array([X[labels == j].mean(axis=0) for j in range(k)])
            if np.allclose(centroids, new_centroids):
                break
            centroids = new_centroids

        return labels

    def _threshold_regimes(self, features: np.ndarray) -> np.ndarray:
        """Threshold-based regime detection using first feature."""
        if features.shape[1] < 1:
            return np.zeros(features.shape[0], dtype=int)

        x = features[:, 0]
        percentiles = np.percentile(x, np.linspace(0, 100, self.config.n_regimes + 1))
        labels = np.digitize(x, percentiles[1:-1])
        return labels

    def _compute_regime_stats(self, features: np.ndarray):
        """Compute statistics for each regime."""
        self._regime_stats = {}
        for regime in range(self.config.n_regimes):
            mask = self._regime_labels == regime
            if mask.any():
                self._regime_stats[regime] = {
                    "count": int(mask.sum()),
                    "mean_return": float(features[mask, 0].mean()) if features.shape[1] > 0 else 0.0,
                    "vol": float(features[mask, 0].std()) if features.shape[1] > 0 else 0.0,
                }

    def predict(self, features: np.ndarray) -> np.ndarray:
        """Predict regime for each sample."""
        if not self._fitted:
            self.fit(features)
        return self._regime_labels

    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        """Soft regime probabilities (distance-based)."""
        if not self._fitted:
            self.fit(features)

        n = features.shape[0]
        k = self.config.n_regimes
        if features.shape[1] >= 2:
            X = features[:, :2]
        else:
            X = features

        # Compute distance to centroids (need to recompute)
        proba = np.zeros((n, k))
        for i in range(n):
            distances = np.sum((features[i, :2] - np.mean(features[self._regime_labels == j][:, :2], axis=0)) ** 2
                               for j in range(k))
            if distances.sum() > 0:
                proba[i] = 1.0 / (1.0 + distances / distances.sum())
            else:
                proba[i] = 1.0 / k

        return proba

    def current_regime(self, features: np.ndarray) -> int:
        """Get current regime (last sample)."""
        labels = self.predict(features)
        return int(labels[-1]) if len(labels) > 0 else 0

    def regime_summary(self) -> dict[int, dict[str, Any]]:
        """Get statistics for each regime."""
        return self._regime_stats.copy()

    def summary(self) -> dict[str, Any]:
        return {
            "model": self.name,
            "fitted": self._fitted,
            "n_regimes": self.config.n_regimes,
            "method": self.config.method,
            "window": self.config.window,
        }


def rolling_regime_labels(features: np.ndarray, window: int = 50, n_regimes: int = 3) -> np.ndarray:
    """Compute rolling regime labels."""
    n = features.shape[0]
    labels = np.full(n, -1, dtype=int)
    detector = RegimeDetector(RegimeConfig(n_regimes=n_regimes, window=window))

    for i in range(window, n):
        window_features = features[i - window:i]
        detector.fit(window_features)
        labels[i] = detector.current_regime(features[i:i + 1])

    return labels


__all__ = [
    "RegimeDetector",
    "RegimeConfig",
    "rolling_regime_labels",
]