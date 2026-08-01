"""Tests for cryptobot.ml.models.regime"""

import numpy as np

from cryptobot.ml.models.regime import (
    RegimeConfig,
    RegimeDetector,
    rolling_regime_labels,
)


def test_regime_detector_kmeans_fit():
    np.random.seed(42)
    n = 200
    # Create 3 distinct regimes
    regime1 = np.random.normal(0.01, 0.01, (n // 3, 2))
    regime2 = np.random.normal(-0.01, 0.02, (n // 3, 2))
    regime3 = np.random.normal(0.0, 0.005, (n - 2 * n // 3, 2))
    features = np.vstack([regime1, regime2, regime3])

    detector = RegimeDetector(RegimeConfig(n_regimes=3, method="kmeans", window=20))
    detector.fit(features)

    assert detector._fitted
    assert detector._regime_labels is not None
    assert len(detector._regime_labels) == len(features)
    assert len(np.unique(detector._regime_labels)) == 3


def test_regime_detector_threshold_method():
    features = np.random.normal(0, 1, (100, 1))
    detector = RegimeDetector(RegimeConfig(n_regimes=3, method="threshold"))
    detector.fit(features)

    assert detector._fitted
    assert len(detector._regime_labels) == len(features)
    assert len(np.unique(detector._regime_labels)) <= 3


def test_regime_detector_predict():
    np.random.seed(42)
    features = np.random.normal(0, 1, (100, 2))
    detector = RegimeDetector(RegimeConfig(n_regimes=2, method="kmeans"))
    detector.fit(features)

    labels = detector.predict(features)
    assert len(labels) == len(features)


def test_regime_detector_predict_proba():
    np.random.seed(42)
    features = np.random.normal(0, 1, (100, 2))
    detector = RegimeDetector(RegimeConfig(n_regimes=2, method="kmeans"))
    detector.fit(features)

    proba = detector.predict_proba(features)
    assert proba.shape == (len(features), 2)
    assert np.allclose(proba.sum(axis=1), 1.0)


def test_current_regime():
    np.random.seed(42)
    features = np.random.normal(0, 1, (50, 2))
    detector = RegimeDetector(RegimeConfig(n_regimes=2, method="kmeans"))
    detector.fit(features)

    regime = detector.current_regime(features)
    assert isinstance(regime, int)
    assert 0 <= regime < 2


def test_rolling_regime_labels():
    np.random.seed(42)
    features = np.random.normal(0, 1, (100, 2))
    labels = rolling_regime_labels(features, window=20, n_regimes=3)

    assert len(labels) == len(features)
    # First window-1 should be -1 (not enough data)
    assert np.all(labels[:20] == -1)
    # After that should have valid labels
    assert np.all(labels[20:] >= 0)


def test_regime_detector_summary():
    np.random.seed(42)
    features = np.random.normal(0, 1, (50, 2))
    detector = RegimeDetector(RegimeConfig(n_regimes=3, method="kmeans"))
    detector.fit(features)

    summary = detector.summary()
    assert summary["model"] == "regime_detector"
    assert summary["fitted"] is True
    assert summary["n_regimes"] == 3
