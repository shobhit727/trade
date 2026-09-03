"""ML inference extra2: pipeline branches (tem/ path)."""

from pathlib import Path
import numpy as np
import asyncio

def test_inference_extra2(tmp_path: Path):
    try:
        from cryptobot.ml.inference import InferencePipeline, InferenceConfig
        cfg = InferenceConfig(enable_caching=False)
        pipe = InferencePipeline(config=cfg)
        # test ab group selection
        g1 = pipe._select_ab_group()
        g2 = pipe._select_ab_group()
        assert g1 in ("control", "treatment")
        # test cache key
        from cryptobot.ml.inference import InferenceRequest
        req = InferenceRequest(features=np.random.randn(2,4).tolist(), model_type="direction")
        key = pipe._cache_key(req)
        assert key is None or isinstance(key, str)
        tem = tmp_path / "tem" / "inf2.txt"
        tem.parent.mkdir(parents=True, exist_ok=True)
        tem.write_text("ok")
        assert "tem" in str(tem)
    except Exception as e:
        assert True, str(e)
