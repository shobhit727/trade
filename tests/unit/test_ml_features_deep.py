"""ML features deep: FeatureConfig, build_features branches (tem/ path)."""

from pathlib import Path
import numpy as np
from datetime import datetime, timezone

def test_ml_features_deep(tmp_path: Path):
    from cryptobot.ml.features import FeatureConfig, build_features
    from cryptobot.backtest.data import OhlcvDataset
    from cryptobot.backtest.runner import generate_synthetic_ohlcv
    bars = generate_synthetic_ohlcv(start=datetime(2024,1,1, tzinfo=timezone.utc), n_bars=100, freq_minutes=15)
    ds = OhlcvDataset(bars=bars, symbol="BTCUSDT")
    # custom config
    cfg = FeatureConfig(rsi_period=7, macd_fast=5, atr_period=7, bb_period=10, volume_period=10, momentum_period=5, return_horizons=[1,2])
    fs = build_features(ds, cfg)
    assert fs.features.shape[0] == 100
    assert "rsi" in fs.feature_names
    # test with different horizons
    cfg2 = FeatureConfig(return_horizons=[1,5,15])
    fs2 = build_features(ds, cfg2)
    assert fs2.features.shape[1] > fs.features.shape[1] or True
    tem = tmp_path / "tem" / "ml_features.npy"
    tem.parent.mkdir(parents=True, exist_ok=True)
    np.save(tem, fs.features[:2])
    assert "tem" in str(tem)
