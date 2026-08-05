from __future__ import annotations

from decimal import Decimal

import pytest

from cryptobot.strategies.ml_strategy import (
    MLStrategyConfig,
    MLStrategy,
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


def test_ml_strategy_retrain_triggers():
    s = MLStrategy(MLStrategyConfig(train_min_samples=3, retrain_every=2))
    s.feed("BTCUSDT", 100)
    s.feed("BTCUSDT", 101)
    s.feed("BTCUSDT", 102)  # Should trigger retrain
    assert s._classifier is not None


__all__ = []