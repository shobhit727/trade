from __future__ import annotations

from decimal import Decimal

from cryptobot.strategies.ml_strategy import (
    MLStrategy,
    MLStrategyConfig,
)


def test_ml_strategy_config_defaults():
    cfg = MLStrategyConfig()
    assert cfg.symbols == ["BTCUSDT"]
    assert cfg.lookback == 100
    assert cfg.horizon == 5
    assert cfg.threshold == 0.55
    assert cfg.train_min_samples == 50
    assert cfg.retrain_every == 20
    assert cfg.quantity == Decimal("1")


def test_ml_strategy_name():
    s = MLStrategy()
    assert s.name == "ml_strategy"


def test_ml_strategy_default_config():
    s = MLStrategy()
    assert isinstance(s.config, MLStrategyConfig)


def test_ml_strategy_custom_config():
    cfg = MLStrategyConfig(
        symbols=["ETHUSDT"],
        lookback=50,
        threshold=0.6,
        quantity=Decimal("0.5"),
    )
    s = MLStrategy(cfg)
    assert s.config.symbols == ["ETHUSDT"]
    assert s.config.lookback == 50
    assert s.config.threshold == 0.6
    assert s.config.quantity == Decimal("0.5")


def test_ml_strategy_returns_none_insufficient_data():
    s = MLStrategy(MLStrategyConfig(lookback=10, train_min_samples=20, horizon=5))
    for p in [100, 101, 102]:
        result = s.feed("BTCUSDT", p)
        assert result is None


def test_ml_strategy_no_signal_before_fitted():
    s = MLStrategy(MLStrategyConfig(train_min_samples=5, retrain_every=3))
    for p in [100, 101, 102, 103, 104, 105]:
        result = s.feed("BTCUSDT", p)
        assert result is None  # Not fitted yet


def test_ml_strategy_multi_symbol_state():
    s = MLStrategy(MLStrategyConfig(train_min_samples=5, horizon=2, retrain_every=3))
    for p in [100, 101, 102, 103, 104, 105, 106, 107]:
        s.feed("BTCUSDT", p)
    for p in [1000, 1010, 1020, 1030, 1040, 1050, 1060, 1070]:
        s.feed("ETHUSDT", p)
    assert "BTCUSDT" in s._prices
    assert "ETHUSDT" in s._prices
    assert s._prices["BTCUSDT"] != s._prices["ETHUSDT"]


def test_ml_strategy_retrain_triggers(monkeypatch):
    # Mock _retrain to set a dummy classifier
    from cryptobot.ml.models.direction import DirectionClassifier, DirectionConfig
    s = MLStrategy(MLStrategyConfig(train_min_samples=3, horizon=1, retrain_every=2))

    def mock_retrain(buf):
        clf = DirectionClassifier(DirectionConfig(threshold=0.55, horizon=1))
        # Create minimal training data
        X = np.array([[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]])
        y = np.array([1])
        clf.fit(X, y)
        s._classifier = clf

    import numpy as np
    monkeypatch.setattr(s, "_retrain", mock_retrain)

    for p in [100, 101, 102, 103]:
        s.feed("BTCUSDT", p)
    assert s._classifier is not None


__all__ = []
