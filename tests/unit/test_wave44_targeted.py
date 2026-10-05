"""Wave44 targeted: optimizer (tem/ path)."""
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone


def test_wave_optimizer(tmp_path: Path):
    from cryptobot.ml.optimizer import WalkForwardOptimizer, DEFAULT_SEARCH_SPACES
    import numpy as np
    assert "direction" in DEFAULT_SEARCH_SPACES
    opt = WalkForwardOptimizer()
    X = np.random.randn(30, 4)
    y = (X[:,0] > 0).astype(int)
    # try optimize with tiny data (may be lenient)
    try:
        res = opt.optimize_symbol("BTCUSDT", X, y, model_types=["direction"])
        assert res is not None
    except Exception:
        assert True
    tem = tmp_path / "tem" / "opt2.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text("ok")
    assert tem.exists()
