
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

from dataclasses import dataclass, field
from typing import Any

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
    volume_period: int = 20
    momentum_period: int = 10
    return_horizons: list[int] = field(default_factory=lambda: [1, 5, 15, 60])


@dataclass
class FeatureSet:
    """Computed feature set with metadata."""
    features: npt.NDArray[np.float64]
    feature_names: list[str]
    timestamps: npt.NDArray[np.datetime64]
    config: FeatureConfig


def _rsi(close: npt.NDArray[np.float64], period: int = 14) -> npt.NDArray[np.float64]:
    """Relative Strength Index."""
    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = np.convolve(gain, np.ones(period) / period, mode="valid")
    avg_loss = np.convolve(loss, np.ones(period) / period, mode="valid")
    rs = np.divide(avg_gain, avg_loss, out=np.zeros_like(avg_gain), where=avg_loss != 0)
    rsi = 100 - (100 / (1 + rs))
    return np.pad(rsi, (period - 1, 0), mode="edge")


def _macd(
    close: npt.NDArray[np.float64],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """MACD line, signal line, histogram."""
    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def _ema(data: npt.NDArray[np.float64], period: int) -> npt.NDArray[np.float64]:
    """Exponential Moving Average."""
    alpha = 2.0 / (period + 1)
    ema = np.zeros_like(data)
    ema[0] = data[0]
    for i in range(1, len(data)):
        ema[i] = alpha * data[i] + (1 - alpha) * ema[i - 1]
    return ema


def _atr(
    high: npt.NDArray[np.float64],
    low: npt.NDArray[np.float64],
    close: npt.NDArray[np.float64],
    period: int = 14,
) -> npt.NDArray[np.float64]:
    """Average True Range."""
    tr1 = high - low
    tr2 = np.abs(high - np.roll(close, 1))
    tr3 = np.abs(low - np.roll(close, 1))
    tr2[0] = 0
    tr3[0] = 0
    tr = np.maximum(np.maximum(tr1, tr2), tr3)
    atr = np.convolve(tr, np.ones(period) / period, mode="valid")
    return np.pad(atr, (period - 1, 0), mode="edge")


def _bollinger_bands(
    close: npt.NDArray[np.float64],
    period: int = 20,
    std_mult: float = 2.0,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Bollinger Bands: middle, upper, lower."""
    sma = np.convolve(close, np.ones(period) / period, mode="valid")
    std = np.array([np.std(close[i - period + 1 : i + 1]) for i in range(period - 1, len(close))])
    middle = sma
    upper = sma + std_mult * std
    lower = sma - std_mult * std
    return (
        np.pad(middle, (period - 1, 0), mode="edge"),
        np.pad(upper, (period - 1, 0), mode="edge"),
        np.pad(lower, (period - 1, 0), mode="edge"),
    )


def _log_volume(volume: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Log volume with zero handling."""
    return np.log1p(volume)


def _volume_ratio(volume: npt.NDArray[np.float64], period: int = 20) -> npt.NDArray[np.float64]:
    """Volume ratio vs rolling average."""
    vol_sma = np.convolve(volume, np.ones(period) / period, mode="valid")
    ratio = volume[period - 1 :] / (vol_sma + 1e-10)
    return np.pad(ratio, (period - 1, 0), mode="edge")


def _momentum(close: npt.NDArray[np.float64], period: int = 10) -> npt.NDArray[np.float64]:
    """Price momentum (rate of change)."""
    mom = np.zeros_like(close)
    mom[period:] = (close[period:] - close[:-period]) / close[:-period]
    return mom


def _returns(close: npt.NDArray[np.float64], horizons: list[int]) -> npt.NDArray[np.float64]:
    """Log returns at multiple horizons."""
    returns = np.zeros((len(close), len(horizons)))
    for j, h in enumerate(horizons):
        if h < len(close):
            returns[h:, j] = np.log(close[h:] / close[:-h])
    return returns


def build_features(
    dataset: OhlcvDataset,
    config: FeatureConfig | None = None,
) -> FeatureSet:
    """Build feature matrix from OHLCV dataset."""
    config = config or FeatureConfig()
    close = dataset.close
    high = dataset.high
    low = dataset.low
    volume = dataset.volume
    timestamps = dataset.timestamps

    features_list = []
    feature_names = []

    # Returns at multiple horizons
    ret = _returns(close, config.return_horizons)
    features_list.append(ret)
    feature_names.extend([f"ret_{h}" for h in config.return_horizons])

    # RSI
    rsi = _rsi(close, config.rsi_period)
    features_list.append(rsi.reshape(-1, 1))
    feature_names.append("rsi")

    # MACD
    macd_line, signal_line, histogram = _macd(
        close, config.macd_fast, config.macd_slow, config.macd_signal
    )
    features_list.append(macd_line.reshape(-1, 1))
    features_list.append(signal_line.reshape(-1, 1))
    features_list.append(histogram.reshape(-1, 1))
    feature_names.extend(["macd", "macd_signal", "macd_hist"])

    # ATR Ratio
    atr = _atr(high, low, close, config.atr_period)
    atr_ratio = atr / (close + 1e-10)
    features_list.append(atr_ratio.reshape(-1, 1))
    feature_names.append("atr_ratio")

    # Bollinger Bands
    bb_middle, bb_upper, bb_lower = _bollinger_bands(close, config.bb_period, config.bb_std)
    bb_position = (close - bb_lower) / (bb_upper - bb_lower + 1e-10)
    bb_width = (bb_upper - bb_lower) / (bb_middle + 1e-10)
    features_list.append(bb_position.reshape(-1, 1))
    features_list.append(bb_width.reshape(-1, 1))
    feature_names.extend(["bb_position", "bb_width"])

    # Log Volume
    log_vol = _log_volume(volume)
    features_list.append(log_vol.reshape(-1, 1))
    feature_names.append("log_volume")

    # Volume Ratio
    vol_ratio = _volume_ratio(volume, config.volume_period)
    features_list.append(vol_ratio.reshape(-1, 1))
    feature_names.append("volume_ratio")

    # Momentum
    mom = _momentum(close, config.momentum_period)
    features_list.append(mom.reshape(-1, 1))
    feature_names.append("momentum")

    features = np.hstack(features_list)

    # Replace NaN/inf with 0
    features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)

    return FeatureSet(
        features=features,
        feature_names=feature_names,
        timestamps=timestamps,
        config=config,
    )


def future_returns(
    close: npt.NDArray[np.float64],
    horizons: list[int],
) -> npt.NDArray[np.float64]:
    """Compute future log returns for labeling."""
    return _returns(close, horizons)


def features_and_labels(
    dataset: OhlcvDataset,
    config: FeatureConfig | None = None,
    label_horizons: list[int] | None = None,
) -> tuple[FeatureSet, npt.NDArray[np.float64]]:
    """Build features and corresponding labels."""
    config = config or FeatureConfig()
    label_horizons = label_horizons or config.return_horizons
    feature_set = build_features(dataset, config)
    labels = future_returns(dataset.close, label_horizons)
    return feature_set, labels


def labels_from_returns(
    returns: npt.NDArray[np.float64],
    threshold: float = 0.0,
) -> npt.NDArray[np.int64]:
    """Convert returns to directional labels: 1 (up), -1 (down), 0 (flat)."""
    labels = np.zeros_like(returns, dtype=np.int64)
    labels[returns > threshold] = 1
    labels[returns < -threshold] = -1
    return labels


def realized_volatility(
    close: npt.NDArray[np.float64],
    window: int = 20,
) -> npt.NDArray[np.float64]:
    """Realized volatility (standard deviation of log returns)."""
    log_ret = np.diff(np.log(close), prepend=np.log(close[0]))
    vol = np.array([np.std(log_ret[max(0, i - window + 1) : i + 1]) for i in range(len(log_ret))])
    return vol * np.sqrt(252 * 24 * 60)  # Annualized assuming minute data


def ewma_volatility(
    close: npt.NDArray[np.float64],
    lam: float = 0.94,
) -> npt.NDArray[np.float64]:
    """Exponentially Weighted Moving Average volatility (RiskMetrics)."""
    log_ret = np.diff(np.log(close), prepend=np.log(close[0]))
    var = np.zeros_like(log_ret)
    var[0] = log_ret[0] ** 2
    for i in range(1, len(log_ret)):
        var[i] = lam * var[i - 1] + (1 - lam) * (log_ret[i] ** 2)
    return np.sqrt(var) * np.sqrt(252 * 24 * 60)


def rolling_regime_labels(
    close: npt.NDArray[np.float64],
    window: int = 100,
    n_regimes: int = 3,
) -> npt.NDArray[np.int64]:
    """Rolling regime labels using volatility clustering."""
    vol = realized_volatility(close, window)
    labels = np.zeros_like(vol, dtype=np.int64)
    for i in range(window, len(vol)):
        window_vol = vol[i - window : i]
        if len(window_vol) > 10:
            quantiles = np.quantile(window_vol, np.linspace(0, 1, n_regimes + 1))
            labels[i] = np.searchsorted(quantiles[1:-1], vol[i])
    return labels


def create_ensemble(
    models: list[Any],
    weights: list[float] | None = None,
) -> Any:
    """Create ensemble from multiple models (placeholder)."""
    from cryptobot.ml.models import EnsembleConfig, EnsembleModel

    config = EnsembleConfig(
        models=[type(m).__name__ for m in models],
        weights=weights or [1.0 / len(models)] * len(models),
    )
    return EnsembleModel(config)
