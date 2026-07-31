from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from cryptobot.ml.features import build_features, future_returns


@dataclass
class DirectionConfig:
    threshold: float = 0.55
    horizon: int = 5
    max_features: int = 8


class DirectionClassifier:
    """Lightweight direction classifier.

    Falls back to a logistic regression implementation that trains without
    sklearn. Tries sklearn LogisticRegression if available for accuracy.
    """

    name = "direction_logreg"

    def __init__(self, config: Optional[DirectionConfig] = None):
        self.config = config or DirectionConfig()
        self._weights: Optional[np.ndarray] = None
        self._bias: float = 0.0
        self._fitted = False
        self._feature_means: Optional[np.ndarray] = None
        self._feature_stds: Optional[np.ndarray] = None

    @staticmethod
    def _sigmoid(z: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-z))

    def fit(self, features: np.ndarray, labels: np.ndarray) -> "DirectionClassifier":
        if features.size == 0:
            self._fitted = False
            return self
        X, self._feature_means, self._feature_stds = self._normalize(features)
        y = labels.astype(float)
        if y.min() < 0 or y.max() > 1:
            y = (y > 0).astype(float)
        try:
            from sklearn.linear_model import LogisticRegression

            clf = LogisticRegression(max_iter=200).fit(X, y)
            self._weights = clf.coef_.ravel()
            self._bias = float(clf.intercept_[0])
        except Exception:
            self._weights, self._bias = self._fit_logreg(X, y)
        self._fitted = True
        return self

    @staticmethod
    def _fit_logreg(X: np.ndarray, y: np.ndarray, lr: float = 0.1, epochs: int = 1000) -> Tuple[np.ndarray, float]:
        n, d = X.shape
        w = np.zeros(d)
        b = 0.0
        for _ in range(epochs):
            z = X @ w + b
            p = 1.0 / (1.0 + np.exp(-z))
            err = p - y
            grad_w = X.T @ err / n
            grad_b = err.mean()
            w -= lr * grad_w
            b -= lr * grad_b
        return w, b

    @staticmethod
    def _normalize(X: np.ndarray, means: Optional[np.ndarray] = None, stds: Optional[np.ndarray] = None) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        if means is None:
            means = X.mean(axis=0)
        if stds is None:
            stds = X.std(axis=0)
        stds = np.where(stds == 0, 1.0, stds)
        return (X - means) / stds, means, stds

    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        if not self._fitted or self._weights is None:
            return np.full(features.shape[0], 0.5)
        X = self._normalize(features, self._feature_means, self._feature_stds)[0]
        z = X @ self._weights + self._bias
        return self._sigmoid(z)

    def predict(self, features: np.ndarray) -> np.ndarray:
        proba = self.predict_proba(features)
        threshold = self.config.threshold
        return (proba > threshold).astype(int)

    def walk_forward_score(
        self,
        features: np.ndarray,
        labels: Optional[np.ndarray] = None,
        n_splits: int = 4,
    ) -> float:
        n = features.shape[0]
        if n <= n_splits + 1:
            return 0.0
        if labels is None:
            labels = (np.random.default_rng(7).uniform(size=n) > 0.5).astype(int)
        scores: List[float] = []
        fold = (n - n_splits - 1) // n_splits
        for k in range(n_splits):
            train_end = (k + 1) * fold
            test_end = train_end + fold
            if test_end > n:
                test_end = n
            X_train = features[:train_end]
            y_train = labels[:train_end]
            X_test = features[train_end:test_end]
            y_test = labels[train_end:test_end]
            if X_train.size == 0 or X_test.size == 0:
                continue
            clf = DirectionClassifier(self.config)
            try:
                clf.fit(X_train, y_train)
                preds = clf.predict(X_test)
                scores.append(float((preds == y_test).mean()))
            except Exception:
                continue
        return float(np.mean(scores)) if scores else 0.0

    def summary(self) -> Dict[str, Any]:
        return {
            "model": self.name,
            "fitted": self._fitted,
            "threshold": self.config.threshold,
            "horizon": self.config.horizon,
        }


def labels_from_returns(returns: np.ndarray, threshold: float = 0.0) -> np.ndarray:
    return (returns > threshold).astype(int)


def features_and_labels(bars, horizon: int = 5) -> Tuple[np.ndarray, np.ndarray]:
    features = build_features(bars)
    future = future_returns(bars, horizon=horizon)
    n_labels = future.size
    n_features = features.shape[0]
    common = min(n_features, n_labels)
    X = features[-common:]
    y = labels_from_returns(future[-common:])
    return X, y


__all__ = [
    "DirectionClassifier",
    "DirectionConfig",
    "features_and_labels",
    "labels_from_returns",
]
