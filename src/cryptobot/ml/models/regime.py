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
        self._centroids: np.ndarray | None = None
        self._threshold_edges: np.ndarray | None = None
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
        centroids = X[rng.choice(n, k, replace=False)].copy()

        for _ in range(100):
            distances = np.sum((X[:, np.newaxis] - centroids) ** 2, axis=2)
            labels = np.argmin(distances, axis=1)
            new_centroids = centroids.copy()
            # An empty cluster used to produce a NaN centroid via mean-of-empty
            # (#48); keep the previous centroid instead so distances stay finite.
            for j in range(k):
                members = X[labels == j]
                if len(members):
                    new_centroids[j] = members.mean(axis=0)
            if np.allclose(centroids, new_centroids):
                break
            centroids = new_centroids

        self._centroids = centroids
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
        self._model = gmm
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
        self._threshold_edges = percentiles[1:-1]
        labels = np.digitize(x, self._threshold_edges)
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

    def _model_input(self, features: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        """Feature slice the fitted model consumes (mirrors each fit() method)."""
        method = RegimeMethod(self.config.method)
        if method is RegimeMethod.HMM and features.shape[1] > 1:
            return features[:, :1]
        if method in (RegimeMethod.KMEANS, RegimeMethod.GMM) and features.shape[1] > 2:
            return features[:, :2]
        return features

    def predict(self, features: npt.NDArray[np.float64]) -> np.ndarray:
        """Predict regimes for NEW samples via the fitted model (issue #36).

        The previous implementation returned ``self._regime_labels`` — the labels
        of the training data — ignoring its argument entirely, so live bars were
        always assigned the last in-sample regime.
        """
        if not self._fitted:
            self.fit(features)
            if not self._fitted:
                return np.zeros(features.shape[0], dtype=int)

        X = self._model_input(features)
        method = RegimeMethod(self.config.method)

        if method is RegimeMethod.HMM and self._model is not None and HAS_HMM:
            try:
                return np.asarray(self._model.predict(X), dtype=int)
            except Exception as e:  # noqa: BLE001 - degenerate sequences fall back
                logger.warning(f"HMM predict failed ({e}); using centroid assignment")
        if method is RegimeMethod.GMM and self._model is not None and HAS_SKLEARN:
            return np.asarray(self._model.predict(X), dtype=int)
        if method is RegimeMethod.THRESHOLD and self._threshold_edges is not None:
            return np.digitize(X[:, 0], self._threshold_edges)

        # k-means (and any fallback): nearest stored centroid
        if self._centroids is None:
            return np.zeros(features.shape[0], dtype=int)
        distances = np.sum(
            (X[:, np.newaxis, :] - self._centroids[np.newaxis, :, :]) ** 2, axis=2
        )
        return np.argmin(distances, axis=1)

    def predict_proba(self, features: npt.NDArray[np.float64]) -> np.ndarray:
        """Soft regime probabilities for NEW samples.

        HMM/GMM expose native posteriors; k-means/threshold use a softmax over
        negative squared distance to the stored fit-time centroids.
        """
        if not self._fitted:
            self.fit(features)
            if not self._fitted:
                n = features.shape[0]
                uniform = np.full((n, max(self.config.n_regimes, 1)), 1.0)
                return uniform / uniform.shape[1]

        k = self.config.n_regimes
        n = features.shape[0]
        X = self._model_input(features)

        if self.config.method == RegimeMethod.HMM and self._model is not None and HAS_HMM and n > 1:
            try:
                proba = np.asarray(self._model.predict_proba(X), dtype=float)
                if proba.shape == (n, k):
                    return proba
            except Exception as e:  # noqa: BLE001
                logger.warning(f"HMM predict_proba failed ({e}); using softmax")

        if self.config.method == RegimeMethod.GMM and self._model is not None and HAS_SKLEARN:
            try:
                proba = np.asarray(self._model.predict_proba(X), dtype=float)
                if proba.shape == (n, k):
                    return proba
            except Exception as e:  # noqa: BLE001
                logger.warning(f"GMM predict_proba failed ({e}); using softmax")

        if self._centroids is None:
            uniform = np.full((n, max(k, 1)), 1.0)
            return uniform / uniform.shape[1]

        distances = np.sum(
            (X[:, np.newaxis, :] - self._centroids[np.newaxis, :, :]) ** 2, axis=2
        )
        exp_neg_dist = np.exp(-distances)
        return exp_neg_dist / exp_neg_dist.sum(axis=1, keepdims=True)

    def current_regime(self, features: npt.NDArray[np.float64]) -> int:
        """Get current regime (last sample)."""
        labels = self.predict(features)
        return int(labels[-1]) if len(labels) > 0 else 0

    def regime_summary(self) -> dict[int, dict[str, Any]]:
        """Get statistics for each regime."""
        return self._regime_stats.copy()

    def summary(self) -> dict[str, Any]:
        method = self.config.method
        if hasattr(method, 'value'):
            method = method.value
        return {
            "model": self.name,
            "fitted": self._fitted,
            "n_regimes": self.config.n_regimes,
            "method": method,
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
