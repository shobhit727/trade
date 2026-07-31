from __future__ import annotations

from typing import Any, Dict, List, Optional
from decimal import Decimal
from dataclasses import fields

from cryptobot.strategies.base import StrategyRegistry, registry
from cryptobot.strategies.mean_reversion import MeanReversionStrategy, MeanReversionConfig
from cryptobot.strategies.trend_following import TrendFollowingStrategy, TrendFollowingConfig
from cryptobot.strategies.stat_arb import StatArbStrategy, StatArbConfig
from cryptobot.strategies.funding_arb import FundingArbStrategy, FundingArbConfig
from cryptobot.strategies.market_making import MarketMakingStrategy, MarketMakingConfig
from cryptobot.strategies.ml_strategy import MLStrategy, MLStrategyConfig


# Map strategy names to (class, config_class) tuples
_STRATEGY_REGISTRY_MAP = {
    "mean_reversion": (MeanReversionStrategy, MeanReversionConfig),
    "trend_following": (TrendFollowingStrategy, TrendFollowingConfig),
    "statistical_arbitrage": (StatArbStrategy, StatArbConfig),
    "funding_arbitrage": (FundingArbStrategy, FundingArbConfig),
    "market_making": (MarketMakingStrategy, MarketMakingConfig),
    "ml_strategy": (MLStrategy, MLStrategyConfig),
}


def _instantiate_config(config_class, config_dict: Dict[str, Any]):
    """Instantiate a config dataclass from a dict, ignoring unknown keys."""
    if config_dict is None:
        config_dict = {}
    valid_keys = {f.name for f in fields(config_class)}
    filtered = {k: v for k, v in config_dict.items() if k in valid_keys}
    return config_class(**filtered)


def load_strategies_from_config(
    strategies_config: Dict[str, Any],
    enabled_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Load and instantiate strategies from config.

    Args:
        strategies_config: Full strategies config dict (from YAML).
        enabled_names: List of strategy names to enable. If None, all enabled strategies are loaded.

    Returns:
        Dict mapping strategy_name -> strategy instance.
    """
    loaded: Dict[str, Any] = {}

    if not strategies_config:
        return loaded

    if enabled_names is None:
        # Load all strategies that have enabled=True in config
        enabled_names = [
            name for name, cfg in strategies_config.items()
            if isinstance(cfg, dict) and cfg.get("enabled", True) and name != "enabled"
        ]

    for name in enabled_names:
        if name not in _STRATEGY_REGISTRY_MAP:
            continue

        strategy_class, config_class = _STRATEGY_REGISTRY_MAP[name]
        strategy_cfg = strategies_config.get(name, {})

        try:
            config_obj = _instantiate_config(config_class, strategy_cfg)
            strategy = strategy_class(config=config_obj)
            loaded[name] = strategy
        except Exception:
            continue

    return loaded


__all__ = [
    "StrategyRegistry",
    "registry",
    "load_strategies_from_config",
    "_STRATEGY_REGISTRY_MAP",
]
