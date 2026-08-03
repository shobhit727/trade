"""cryptobot_rs - Rust performance layer for Cryptobot

Python bindings to the Rust crates:
- cryptobot_rs.features: Feature engineering (returns, volatility, RSI, MACD, etc.)
- cryptobot_rs.risk: Risk math (Kelly, position sizing, correlation)
- cryptobot_rs.orderbook: Order book operations, VPIN
- cryptobot_rs.backtest: Performance metrics, fill simulator
"""

from cryptobot_rs.features import (
    log_returns,
    simple_returns,
    realized_volatility,
    ewma_volatility,
    ema,
    macd,
    rsi,
    bollinger_bands,
)

from cryptobot_rs.risk import (
    kelly_fraction,
    kelly_from_stats,
    fixed_fraction,
    vol_target,
    max_abs_correlation,
)

from cryptobot_rs.orderbook import (
    OrderBook,
    vpin,
)

from cryptobot_rs.backtest import (
    PerformanceMetrics,
    calculate_metrics,
    simulate_fill,
)

__version__ = "0.1.0"
__all__ = [
    "log_returns",
    "simple_returns",
    "realized_volatility",
    "ewma_volatility",
    "ema",
    "macd",
    "rsi",
    "bollinger_bands",
    "kelly_fraction",
    "kelly_from_stats",
    "fixed_fraction",
    "vol_target",
    "max_abs_correlation",
    "OrderBook",
    "vpin",
    "PerformanceMetrics",
    "calculate_metrics",
    "simulate_fill",
]