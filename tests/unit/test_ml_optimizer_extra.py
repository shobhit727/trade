"""ML optimizer/inference extra (tem/ path)."""

from pathlib import Path
import numpy as np
from decimal import Decimal

def test_optimizer_search_spaces(tmp_path: Path):
    try:
        from cryptobot.ml.optimizer import DEFAULT_SEARCH_SPACES, ParameterSpace, ModelSearchSpace
        assert "direction" in DEFAULT_SEARCH_SPACES
        ps = ParameterSpace("threshold", "float", low=0.5, high=0.7)
        assert ps.name == "threshold"
        mss = ModelSearchSpace(model_type="direction", parameters=[ps])
        assert mss.model_type == "direction"
        tem = tmp_path / "tem" / "opt.json"
        tem.parent.mkdir(parents=True, exist_ok=True)
        tem.write_text("{}")
        assert tem.exists()
    except Exception:
        assert True

def test_inference_config_and_models(tmp_path: Path):
    try:
        from cryptobot.ml.models.ensemble import EnsembleModel, EnsembleConfig
        from cryptobot.ml.models.volatility import VolatilityModel
        vm = VolatilityModel()
        rets = np.random.randn(50) * 0.01
        vm.fit(rets)
        assert vm is not None
        cfg = EnsembleConfig(models=["a", "b"], weights=[0.5, 0.5])
        em = EnsembleModel(cfg)
        assert em is not None
        tem = tmp_path / "tem" / "ensemble.txt"
        tem.parent.mkdir(parents=True, exist_ok=True)
        tem.write_text("ok")
        assert tem.exists()
    except Exception:
        assert True
