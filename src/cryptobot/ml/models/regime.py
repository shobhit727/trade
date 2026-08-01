from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import numpy as np
import numpy.typing as npt

try:
    from hmmlearn import hmm
    HAS_HMM = True
except ImportError:
    HAS_HMM = False

try:
    from sklearn.mixture import GaussianMixture
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

from cryptobot.utils.logging import get_logger

logger = get_logger(__name__)


class RegimeMethod(StrEnum):
    HMM = "hmm"
    KMEANS = "kmeans"
    GMM = "gmm"
    THRESHOLD = "threshold"


@dataclass
class RegimeConfig:
    n_regimes: int = 3
    window: int = 50
    method: RegimeMethod = RegimeMethod.HMM
    min_duration: int = 5
    n_init: int = 10
    covariance_type: str = "full"
    random_state: int = 42


class RegimeDetector:
    """
    Market regime detection supporting multiple methods:
    - Hidden Markov Model (HMM)
    - K-means clustering
    - Gaussian Mixture Model (GMM)
    - Threshold-based rules
    """

    name = "regime_detector"

    def __init__(self, config: RegimeConfig | None = None):
        self.config = config or RegimeConfig()
        self._fitted = False
        self._regime_labels: np.ndarray | None = None
        self._regime_stats: dict[int, dict[str, float]] = {}
        self._model: Any = None
        self._transition_matrix: np.ndarray | None = None
        self._regime_means: np.ndarray | None = None
        self._regime_covs: np.ndarray | None = None

    def fit(self, features: npt.NDArray[np.float64]) -> RegimeDetector:
        """Fit regime detector on feature matrix."""
        n = features.shape[0]
        if n < self.config.window:
            self._fitted = False
            return self

        if self.config.method == RegimeMethod.KMEANS:
            self._regime_labels = self._kmeans_regimes(features)
        elif self.config.method == RegimeMethod.GMM:
            self._regime_labels = self._gmm_regimes(features)
        elif self.config.method == RegimeMethod.HMM:
            self._regime_labels = self._hmm_regimes(features)
        else:
            self._regime_labels = self._threshold_regimes(features)

        self._compute_regime_stats(features)
        self._fitted = True
        return self

    def _kmeans_regimes(self, features: npt.NDArray[np.float64]) -> np.ndarray:
        """Simple k-means clustering for regimes."""
        if not HAS_SKLEARN:
            logger.warning("sklearn not available, using threshold method")
            return self._threshold_regimes(features)

        n = features.shape[0]
        k = self.config.n_regimes

        # Use first 2 features or first 2 PCs
        if features.shape[1] >= 2:
            X = features[:, :2]
        else:
            X = features

        # Simple k-means
        rng = np.random.default_rng(self.config.random_state)
        centroids = X[rng.choice(n, k, replace=False)]

        for _ in range(100):
            distances = np.sum((X[:, np.newaxis] - centroids) ** 2, axis=2)
            labels = np.argmin(distances, axis=1)
            new_centroids = np.array([X[labels == j].mean(axis=0) for j in range(k)])
            if np.allclose(centroids, new_centroids):
                break
            centroids = new_centroids

        return labels

    def _gmm_regimes(self, features: npt.NDArray[np.float64]) -> np.ndarray:
        """Gaussian Mixture Model for regime detection."""
        if not HAS_SKLEARN:
            logger.warning("sklearn not available, using k-means")
            return self._kmeans_regimes(features)

        k = self.config.n_regimes

        # Use first 2 features for 2D visualization
        if features.shape[1] >= 2:
            X = features[:, :2]
        else:
            X = features

        gmm = GaussianMixture(
            n_components=k,
            covariance_type=self.config.covariance_type,
            n_init=self.config.n_init,
            random_state=self.config.random_state
        )
        labels = gmm.fit_predict(X)
        return labels

    def _hmm_regimes(self, features: npt.NDArray[np.float64]) -> np.ndarray:
        """Hidden Markov Model for regime detection."""
        if not HAS_HMM:
            logger.warning("hmmlearn not available, using k-means")
            return self._kmeans_regimes(features)

        k = self.config.n_regimes

        # Use first feature (returns) for HMM
        if features.shape[1] >= 1:
            X = features[:, :1]
        else:
            X = features

        model = hmm.GaussianHMM(
            n_components=k,
            covariance_type=self.config.covariance_type,
            n_iter=100,
            random_state=self.config.random_state
        )

        try:
            model.fit(X)
            labels = model.predict(X)
            self._model = model
            self._transition_matrix = model.transmat_
            self._regime_means = model.means_
            self._regime_covs = model.covars_
        except Exception as e:
            logger.warning(f"HMM fitting failed: {e}, falling back to k-means")
            return self._kmeans_regimes(features)

        return labels

    def _threshold_regimes(self, features: npt.NDArray[np.float64]) -> np.ndarray:
        """Threshold-based regime detection using first feature."""
        if features.shape[1] < 1:
            return np.zeros(features.shape[0], dtype=int)

        x = features[:, 0]
        percentiles = np.percentile(x, np.linspace(0, 100, self.config.n_regimes + 1))
        labels = np.digitize(x, percentiles[1:-1])
        return labels

    def _compute_regime_stats(self, features: npt.NDArray[np.float64]) -> None:
        """Compute statistics for each regime."""
        self._regime_stats = {}
        for regime in range(self.config.n_regimes):
            mask = self._regime_labels == regime
            if mask.any():
                regime_features = features[mask]
                self._regime_stats[regime] = {
                    "count": int(mask.sum()),
                    "mean_return": float(regime_features[:, 0].mean()) if regime_features.shape[1] > 0 else 0.0,
                    "vol": float(regime_features[:, 0].std()) if regime_features.shape[1] > 0 else 0.0,
                    "mean_features": regime_features.mean(axis=0).tolist(),
                    "std_features": regime_features.std(axis=0).tolist(),
                }

    def predict(self, features: npt.NDArray[np.float64]) -> np.ndarray:
        """Predict regime for each sample."""
        if not self._fitted:
            self.fit(features)
        return self._regime_labels

    def predict_proba(self, features: npt.NDArray[np.float64]) -> np.ndarray:
        """Soft regime probabilities (distance-based softmax)."""
        if not self._fitted:
            self.fit(features)

        n = features.shape[0]
        k = self.config.n_regimes

        if features.shape[1] >= 2:
            X = features[:, :2]
        else:
            X = features

        # Get centroids from fitted model
        centroids = []
        for j in range(k):
            mask = self._regime_labels == j
            if mask.any():
                if features.shape[1] >= 2:
                    centroids.append(features[mask, :2].mean(axis=0))
                else:
                    centroids.append(features[mask].mean(axis=0))
            else:
                centroids.append(np.zeros(features.shape[1]))

        centroids = np.array(centroids)
        if features.shape[1] >= 2:
            X = features[:, :2]
        else:
            X = features

        proba = np.zeros((n, k))
        for i in range(n):
            distances = np.sum((X[i] - centroids) ** 2, axis=1)
            # Softmax on negative distances (closer = higher probability)
            exp_neg_dist = np.exp(-distances)
            proba[i] = exp_neg_dist / exp_neg_dist.sum()

        return proba

    def current_regime(self, features: npt.NDArray[np.float64]) -> int:
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
            "method": self.config.method.value,
            "window": self.config.window,
            "transition_matrix": self._transition_matrix.tolist() if self._transition_matrix is not None else None,
        }


def rolling_regime_labels(
    features: npt.NDArray[np.float64],
    window: int = 50,
    n_regimes: int = 3
) -> np.ndarray:
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
    "RegimeMethod",
    "rolling_regime_labels",
]
