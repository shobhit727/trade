from __future__ import annotations

"""
Feature Engineering Pipeline

Provides 8 core features for ML models:
1. Returns (log returns at multiple horizons)
2. RSI (Relative Strength Index)
3. MACD (Moving Average Convergence Divergence)
4. ATR Ratio (Average True Range ratio)
5. Bollinger Bands Position + Width
6. Log Volume
7. Volume Ratio
9. Price Momentum
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt

from cryptobot.backtest.data import OhlcvDataset


@dataclass
class FeatureConfig:
    """Configuration for feature computation."""
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    atr_period: int = 14
    bb_period: int = 20
    bb_std: float = 2.0
    volume_lookback: int = 20
    momentum_periods: list[int] = field(default_factory=lambda: [1, 5, 15, 60])


@dataclass
class FeatureSet:
    """Container for computed features."""
    returns: npt.NDArray[np.float64]          # Log returns
    rsi: npt.NDArray[np.float64]              # RSI values
    macd: npt.NDArray[np.float64]             # MACD line
    macd_signal: npt.NDArray[np.float64]      # MACD signal line
    macd_histogram: npt.NDArray[np.float64]   # MACD histogram
    atr_ratio: npt.NDArray[np.float64]        # ATR / close price
    bb_position: npt.NDArray[np.float64]      # Position within Bollinger Bands (0-1)
    bb_width: npt.NDArray[np.float64]         # Bollinger Band width
    log_volume: npt.NDArray[np.float64]       # Log volume
    volume_ratio: npt.NDArray[np.float64]     # Volume / rolling avg volume
    momentum: dict[int, npt.NDArray[np.float64]]  # Momentum at different periods
    timestamps: npt.NDArray[np.datetime64]     # Timestamps for each row

    def to_array(self) -> npt.NDArray[np.float64]:
        """Convert features to 2D array for ML models (n_samples, n_features)."""
        features = [
            self.returns,
            self.rsi,
            self.macd,
            self.macd_signal,
            self.macd_histogram,
            self.atr_ratio,
            self.bb_position,
            self.bb_width,
            self.log_volume,
            self.volume_ratio,
        ]
        for period in sorted(self.momentum.keys()):
            features.append(self.momentum[period])
        return np.column_stack(features)

    def feature_names(self) -> list[str]:
        """Get feature names in order."""
        names = [
            "returns", "rsi", "macd", "macd_signal", "macd_histogram",
            "atr_ratio", "bb_position", "bb_width", "log_volume", "volume_ratio"
        ]
        for period in sorted(self.momentum.keys()):
            names.append(f"momentum_{period}")
        return names


def compute_returns(prices: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Compute log returns."""
    returns = np.zeros_like(prices)
    returns[1:] = np.log(prices[1:] / prices[:-1])
    return returns


def compute_rsi(prices: npt.NDArray[np.float64], period: int = 14) -> npt.NDArray[np.float64]:
    """Compute RSI (Relative Strength Index)."""
    if len(prices) < period + 1:
        return np.full(len(prices), 50.0)

    returns = np.diff(prices)
    gains = np.where(returns > 0, returns, 0.0)
    losses = np.where(returns < 0, -returns, 0.0)

    avg_gain = np.zeros_like(prices)
    avg_loss = np.zeros_like(prices)

    # Initial average
    avg_gain[period] = np.mean(gains[:period])
    avg_loss[period] = np.mean(losses[:period])

    # Smooth
    for i in range(period + 1, len(prices)):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gains[i - 1]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + losses[i - 1]) / period

    rs = np.where(avg_loss > 0, avg_gain / avg_loss, 0)
    rsi = 100 - (100 / (1 + rs))
    rsi[:period] = 50.0  # Neutral for initial period
    return rsi


def compute_macd(
    prices: npt.NDArray[np.float64],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Compute MACD line, signal line, and histogram."""
    ema_fast = pd_ema(prices, fast)
    ema_slow = pd_ema(prices, slow)
    macd_line = ema_fast - ema_slow
    signal_line = pd_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def pd_ema(series: npt.NDArray[np.float64], period: int) -> npt.NDArray[np.float64]:
    """Pandas-style exponential moving average."""
    alpha = 2.0 / (period + 1)
    ema = np.zeros_like(series)
    ema[0] = series[0]
    for i in range(1, len(series)):
        ema[i] = alpha * series[i] + (1 - alpha) * ema[i - 1]
    return ema


def compute_atr(
    high: npt.NDArray[np.float64],
    low: npt.NDArray[np.float64],
    close: npt.NDArray[np.float64],
    period: int = 14
) -> npt.NDArray[np.float64]:
    """Compute Average True Range."""
    if len(high) < 2:
        return np.zeros_like(close)

    tr = np.zeros_like(close)
    tr[0] = high[0] - low[0]
    for i in range(1, len(close)):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1])
        )

    atr = np.zeros_like(close)
    atr[:period] = np.mean(tr[:period])
    for i in range(period, len(close)):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

    return atr


def compute_bollinger_bands(
    prices: npt.NDArray[np.float64],
    period: int = 20,
    std_dev: float = 2.0
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Compute Bollinger Bands (upper, middle, lower)."""
    if len(prices) < period:
        return np.full_like(prices, np.nan), np.full_like(prices, np.nan), np.full_like(prices, np.nan)

    middle = np.full_like(prices, np.nan)
    upper = np.full_like(prices, np.nan)
    lower = np.full_like(prices, np.nan)

    for i in range(period - 1, len(prices)):
        window = prices[i - period + 1:i + 1]
        mid = np.mean(window)
        std = np.std(window, ddof=0)
        middle[i] = mid
        upper[i] = mid + std_dev * std
        lower[i] = mid - std_dev * std

    return upper, middle, lower


def compute_features(dataset: OhlcvDataset, config: FeatureConfig | None = None) -> FeatureSet:
    """
    Compute all features from OHLCV dataset.

    Args:
        dataset: OHLCV dataset with bars
        config: Feature computation configuration

    Returns:
        FeatureSet with all computed features
    """
    config = config or FeatureConfig()
    bars = dataset.bars

    # Extract arrays
    len(bars)
    np.array([float(b.open_price) for b in bars], dtype=np.float64)
    highs = np.array([float(b.high_price) for b in bars], dtype=np.float64)
    lows = np.array([float(b.low_price) for b in bars], dtype=np.float64)
    closes = np.array([float(b.close_price) for b in bars], dtype=np.float64)
    volumes = np.array([float(b.volume) for b in bars], dtype=np.float64)
    timestamps = np.array([b.open_time for b in bars], dtype=np.datetime64)

    # Compute features
    returns = compute_returns(closes)
    rsi = compute_rsi(closes, config.rsi_period)
    macd_line, macd_signal, macd_hist = compute_macd(
        closes, config.macd_fast, config.macd_slow, config.macd_signal
    )
    atr = compute_atr(highs, lows, closes, config.atr_period)
    atr_ratio = np.where(closes > 0, atr / closes, 0)

    bb_upper, bb_middle, bb_lower = compute_bollinger_bands(
        closes, config.bb_period, config.bb_std
    )
    bb_width = np.where(bb_middle > 0, (bb_upper - bb_lower) / bb_middle, 0)
    bb_position = np.where(
        (bb_upper - bb_lower) > 0,
        (closes - bb_lower) / (bb_upper - bb_lower),
        0.5
    )

    log_volume = np.log(np.maximum(volumes, 1))
    vol_ma = pd_ema(volumes.astype(np.float64), config.volume_lookback)
    volume_ratio = np.where(vol_ma > 0, volumes / vol_ma, 1.0)

    momentum = {}
    for period in config.momentum_periods:
        if len(closes) > period:
            mom = np.zeros_like(closes)
            mom[period:] = (closes[period:] - closes[:-period]) / closes[:-period]
        else:
            mom = np.zeros_like(closes)
        momentum[period] = mom

    return FeatureSet(
        returns=returns,
        rsi=rsi,
        macd=macd_line,
        macd_signal=macd_signal,
        macd_histogram=macd_hist,
        atr_ratio=atr_ratio,
        bb_position=bb_position,
        bb_width=bb_width,
        log_volume=log_volume,
        volume_ratio=volume_ratio,
        momentum=momentum,
        timestamps=timestamps,
    )


__all__ = [
    "FeatureConfig",
    "FeatureSet",
    "compute_features",
    "compute_returns",
    "compute_rsi",
    "compute_macd",
    "compute_atr",
    "compute_bollinger_bands",
    "pd_ema",
]
