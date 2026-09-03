"""Wave46 targeted: regime (tem/ path)."""
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone


def test_wave_regime(tmp_path: Path):
    import numpy as np
    from cryptobot.ml.models.regime import RegimeDetector
    det = RegimeDetector()
    feats = np.random.randn(40, 3)
    det.fit(feats)
    preds = det.predict(np.random.randn(5, 3))
    assert len(preds) == 5
    proba = det.predict_proba(np.random.randn(5, 3))
    assert proba.shape[0] == 5
    tem = tmp_path / "tem" / "regime2.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text("ok")
    assert "tem" in str(tem)
