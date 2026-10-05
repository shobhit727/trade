"""Data features extra2: more branches (tem/ path)."""

from pathlib import Path
import numpy as np
from datetime import datetime, timezone

def test_features_extra2(tmp_path: Path):
    from cryptobot.ml.features import FeatureConfig, build_features
    from cryptobot.backtest.data import OhlcvDataset
    from cryptobot.backtest.runner import generate_synthetic_ohlcv
    bars = generate_synthetic_ohlcv(start=datetime(2024,1,1, tzinfo=timezone.utc), n_bars=60, freq_minutes=15)
    ds = OhlcvDataset(bars=bars, symbol="ETHUSDT")
    # edge: tiny horizon
    cfg = FeatureConfig(return_horizons=[1], rsi_period=7, volume_period=5)
    fs = build_features(ds, cfg)
    assert fs.features.shape[0] == 60
    tem = tmp_path / "tem" / "features2.npy"
    tem.parent.mkdir(parents=True, exist_ok=True)
    np.save(tem, fs.features[:2])
    assert "tem" in str(tem)
