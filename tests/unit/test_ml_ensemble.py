"""Tests for cryptobot.ml.models.ensemble"""

from __future__ import annotations

import numpy as np
import pytest

from cryptobot.ml.models.ensemble import (
    EnsembleModel,
    EnsembleConfig,
    create_ensemble,
)
from cryptobot.ml.models.direction import DirectionConfig
from cryptobot.ml.models.volatility import VolatilityConfig
from cryptobot.ml.models.regime import RegimeConfig


def test_ensemble_fit_and_predict():
    np.random.seed(42)
    n = 200
    features = np.random.normal(0, 1, (n, 5))
    labels = (np.random.normal(0, 1, n) > 0).astype(int)

    config = EnsembleConfig(
        models=["direction", "regime"],
        weights=[0.6, 0.4],
    )
    ensemble = EnsembleModel(config).fit(features, labels)

    assert ensemble._fitted
    assert "direction" in ensemble.models
    assert "regime" in ensemble.models

    preds = ensemble.predict(features)
    assert len(preds) == n
    assert set(np.unique(preds)).issubset({0, 1})


def test_ensemble_predict_proba():
    np.random.seed(42)
    n = 100
    features = np.random.normal(0, 1, (n, 5))
    labels = (np.random.normal(0, 1, n) > 0).astype(int)

    config = EnsembleConfig(models=["direction", "regime"])
    ensemble = EnsembleModel(config).fit(features, labels)

    proba = ensemble.predict_proba(features)
    assert proba.shape == (n, 2)
    assert np.allclose(proba.sum(axis=1), 1.0)


def test_ensemble_with_all_models():
    np.random.seed(42)
    n = 100
    features = np.random.normal(0, 1, (n, 5))
    labels = (np.random.normal(0, 1, n) > 0).astype(int)

    config = EnsembleConfig(
        models=["direction", "volatility", "regime"],
        weights=[0.5, 0.2, 0.3],
    )
    ensemble = EnsembleModel(config).fit(features, labels)

    assert "direction" in ensemble.models
    assert "volatility" in ensemble.models
    assert "regime" in ensemble.models

    preds, conf = ensemble.predict_with_confidence(features)
    assert len(preds) == n
    assert len(conf) == n
    assert np.all(conf >= 0) and np.all(conf <= 1)


def test_ensemble_predict_volatility():
    np.random.seed(42)
    n = 100
    features = np.random.normal(0, 1, (n, 5))
    labels = np.random.normal(0.01, 0.02, n)

    config = EnsembleConfig(models=["volatility"])
    ensemble = EnsembleModel(config).fit(features, labels)

    vol = ensemble.predict_volatility(labels, horizon=5)
    assert vol >= 0


def test_ensemble_current_regime():
    np.random.seed(42)
    n = 50
    features = np.random.normal(0, 1, (n, 3))
    labels = np.random.normal(0, 1, n)

    config = EnsembleConfig(models=["regime"])
    ensemble = EnsembleModel(config).fit(features, labels)

    regime = ensemble.current_regime(features)
    assert isinstance(regime, int)
    assert regime >= 0


def test_create_ensemble_helper():
    ensemble = create_ensemble(
        direction_weight=0.5,
        volatility_weight=0.2,
        regime_weight=0.3,
    )

    assert isinstance(ensemble, EnsembleModel)
    assert ensemble.config.weights is not None
    assert len(ensemble.config.weights) == 3