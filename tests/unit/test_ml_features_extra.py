"""ML features extra: build_features branches (tem/ path)."""

from pathlib import Path
import numpy as np
from datetime import datetime, timezone

def test_ml_features_extra(tmp_path: Path):
    from cryptobot.ml.features import build_features, FeatureConfig
    from cryptobot.backtest.data import OhlcvDataset
    from cryptobot.backtest.runner import generate_synthetic_ohlcv, OhlcvBar
    # synthetic with volume
    bars = generate_synthetic_ohlcv(start=datetime(2024,1,1, tzinfo=timezone.utc), n_bars=50, freq_minutes=15)
    ds = OhlcvDataset(bars=bars, symbol="BTCUSDT")
    cfg = FeatureConfig(return_horizons=[1,5], rsi_period=14, volume_period=20)
    fs = build_features(ds, cfg)
    assert fs.features.shape[0] == 50
    assert len(fs.feature_names) >= 10
    # test FeatureSet.to_array
    arr = fs.to_array()
    assert arr.shape == fs.features.shape
    tem = tmp_path / "tem" / "features.npy"
    tem.parent.mkdir(parents=True, exist_ok=True)
    np.save(tem, arr[:2])
    assert "tem" in str(tem)

def test_ml_features_edge(tmp_path: Path):
    from cryptobot.ml.features import realized_volatility, ewma_volatility, rolling_regime_labels
    close = np.array([100+ i*0.1 + np.random.randn()*0.5 for i in range(50)], dtype=float)
    vol = realized_volatility(close, window=20)
    assert len(vol) == len(close)
    evol = ewma_volatility(close, lam=0.94)
    assert len(evol) == len(close)
    labels = rolling_regime_labels(close, window=20, n_regimes=3)
    assert len(labels) == len(close)
    tem = tmp_path / "tem" / "vol.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text("ok")
    assert tem.exists()
