from __future__ import annotations

from cryptobot.strategies.registry import (
    _STRATEGY_REGISTRY_MAP,
    _instantiate_config,
    load_strategies_from_config,
)


def test_strategy_registry_map_contains_all_strategies():
    assert "mean_reversion" in _STRATEGY_REGISTRY_MAP
    assert "trend_following" in _STRATEGY_REGISTRY_MAP
    assert "statistical_arbitrage" in _STRATEGY_REGISTRY_MAP
    assert "funding_arbitrage" in _STRATEGY_REGISTRY_MAP
    assert "market_making" in _STRATEGY_REGISTRY_MAP
    assert "ml_strategy" in _STRATEGY_REGISTRY_MAP


def test_instantiate_config_filters_unknown_keys():
    from cryptobot.strategies.mean_reversion import MeanReversionConfig

    cfg = _instantiate_config(
        MeanReversionConfig,
        {"lookback": 20, "z_entry": 2.5, "nonexistent_key": "ignore_me"},
    )
    assert cfg.lookback == 20
    assert cfg.z_entry == 2.5
    assert not hasattr(cfg, "nonexistent_key")


def test_instantiate_config_none():
    from cryptobot.strategies.mean_reversion import MeanReversionConfig

    cfg = _instantiate_config(MeanReversionConfig, None)
    assert isinstance(cfg, MeanReversionConfig)


def test_load_strategies_empty_config():
    loaded = load_strategies_from_config({})
    assert loaded == {}


def test_load_strategies_selects_enabled():
    cfg = {
        "mean_reversion": {"enabled": True, "lookback": 20},
        "trend_following": {"enabled": False, "lookback": 50},
    }
    loaded = load_strategies_from_config(cfg)
    assert "mean_reversion" in loaded
    assert "trend_following" not in loaded


def test_load_strategies_explicit_enabled_names():
    cfg = {
        "mean_reversion": {"enabled": False, "lookback": 20},
        "trend_following": {"enabled": True, "lookback": 50},
    }
    loaded = load_strategies_from_config(cfg, enabled_names=["trend_following"])
    assert "trend_following" in loaded
    assert "mean_reversion" not in loaded


def test_load_strategies_skip_unknown_name():
    cfg = {"unknown_strategy": {"enabled": True}}
    loaded = load_strategies_from_config(cfg)
    assert loaded == {}


def test_load_strategies_handles_top_level_enabled():
    cfg = {
        "enabled": True,
        "mean_reversion": {"enabled": True, "lookback": 20},
    }
    loaded = load_strategies_from_config(cfg)
    assert "enabled" not in loaded
    assert "mean_reversion" in loaded


def test_load_strategies_returns_instances():
    cfg = {
        "mean_reversion": {"enabled": True, "lookback": 30},
    }
    loaded = load_strategies_from_config(cfg)
    strat = loaded["mean_reversion"]
    assert strat.config.lookback == 30


__all__ = []
