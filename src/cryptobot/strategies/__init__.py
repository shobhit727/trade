from cryptobot.strategies.base import BaseStrategy, MeanReversionStrategy as MeanReversionStrategyPlaceholder, StrategyRegistry, registry

try:
    from cryptobot.strategies.mean_reversion import MeanReversionConfig, MeanReversionStrategy
except Exception:
    MeanReversionConfig = None
    MeanReversionStrategy = None

try:
    from cryptobot.strategies.trend_following import TrendFollowingConfig, TrendFollowingStrategy
except Exception:
    TrendFollowingConfig = None
    TrendFollowingStrategy = None

__all__ = [
    "BaseStrategy",
    "MeanReversionStrategyPlaceholder",
    "StrategyRegistry",
    "TrendFollowingConfig",
    "TrendFollowingStrategy",
    "MeanReversionConfig",
    "MeanReversionStrategy",
    "registry",
]
