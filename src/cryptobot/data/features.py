"""Feature computation for market data.

This module re-exports the canonical feature pipeline from `cryptobot.ml.features`.
Use `cryptobot.ml.features` directly for new code; this path exists for backward
compatibility with existing references.
"""

from cryptobot.ml.features import (
    build_features,
    compute_atr_ratio,
    compute_bollinger,
    compute_log_volume,
    compute_macd,
    compute_returns,
    compute_rsi,
    future_returns,
)

__all__ = [
    "build_features",
    "future_returns",
    "compute_returns",
    "compute_rsi",
    "compute_macd",
    "compute_atr_ratio",
    "compute_bollinger",
    "compute_log_volume",
]
