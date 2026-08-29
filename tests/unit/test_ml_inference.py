from __future__ import annotations

from cryptobot.ml.inference import (
    InferenceConfig,
    InferenceMode,
    InferenceRequest,
    InferenceResponse,
    ModelCache,
    ModelRegistry,
    ModelVersion,
)


def test_inference_config_defaults():
    cfg = InferenceConfig()
    assert cfg.mode == InferenceMode.SYNC
    assert cfg.model_version == ModelVersion.LATEST
    assert cfg.cache_ttl_seconds == 60
    assert cfg.batch_size == 32


def test_inference_mode_enum():
    assert InferenceMode.SYNC.value == "sync"
    assert InferenceMode.ASYNC.value == "async"
    assert InferenceMode.BATCH.value == "batch"


def test_model_version_enum():
    assert ModelVersion.LATEST.value == "latest"
    assert ModelVersion.STABLE.value == "stable"
    assert ModelVersion.SPECIFIC.value == "specific"


def test_inference_request_defaults():
    req = InferenceRequest()
    assert req.request_id is not None
    assert req.timestamp is not None
    assert req.model_type == "ensemble"
    assert req.version == ModelVersion.LATEST


def test_inference_response_defaults():
    resp = InferenceResponse()
    assert resp.request_id == ""
    assert resp.model_type == ""
    assert resp.version == ""
    assert resp.predictions is None
    assert resp.probabilities is None
    assert resp.confidence is None
    assert resp.regime is None


def test_model_cache_get_set():
    import asyncio
    cache = ModelCache(ttl_seconds=60)
    asyncio.run(cache.set("key1", "value1"))
    result = asyncio.run(cache.get("key1"))
    assert result == "value1"


def test_model_cache_miss():
    import asyncio
    cache = ModelCache(ttl_seconds=60)
    result = asyncio.run(cache.get("nonexistent"))
    assert result is None


def test_model_cache_expires():
    import asyncio
    cache = ModelCache(ttl_seconds=0)  # immediate expiry
    asyncio.run(cache.set("key1", "value1"))
    # Should expire immediately
    result = asyncio.run(cache.get("key1"))
    assert result is None


def test_model_cache_clear():
    import asyncio
    cache = ModelCache(ttl_seconds=60)
    asyncio.run(cache.set("key1", "value1"))
    asyncio.run(cache.clear())
    result = asyncio.run(cache.get("key1"))
    assert result is None


def test_model_registry_register_get():
    import asyncio
    reg = ModelRegistry()
    asyncio.run(reg.register("direction", "model1", version="v1"))
    model = asyncio.run(reg.get("direction", specific_version="v1"))
    assert model == "model1"


def test_model_registry_list_versions():
    import asyncio
    reg = ModelRegistry()
    asyncio.run(reg.register("direction", "model1", version="v1"))
    asyncio.run(reg.register("direction", "model2", version="v2"))
    versions = asyncio.run(reg.list_versions("direction"))
    assert "v1" in versions
    assert "v2" in versions


def test_model_registry_get_latest():
    import asyncio
    reg = ModelRegistry()
    asyncio.run(reg.register("direction", "model1", version="v1"))
    asyncio.run(reg.register("direction", "model2", version="v2"))
    # Latest by registration time
    model = asyncio.run(reg.get("direction", specific_version=None))
    # Should get one of them (the last one registered)
    assert model in ("model1", "model2")


def test_cache_key_consistent_and_includes_version():
    import numpy as np

    from cryptobot.ml.inference import InferencePipeline

    req = InferenceRequest(model_type="direction", features=np.zeros((4, 3)))
    k1 = InferencePipeline._cache_key(None, req)
    k2 = InferencePipeline._cache_key(None, req)
    assert k1 == k2
    assert k1 is not None
    # The model version must be part of the key; the original bug dropped it,
    # so the store key never matched the lookup key (issue #48).
    assert "latest" in k1


def test_cache_key_none_when_features_absent():
    from cryptobot.ml.inference import InferencePipeline

    req = InferenceRequest(model_type="direction", features=None)
    assert InferencePipeline._cache_key(None, req) is None


def test_inference_cache_hit_uses_same_key():
    import asyncio
    import numpy as np

    from cryptobot.ml.inference import (
        InferenceConfig,
        InferencePipeline,
        InferenceRequest,
    )

    class FakeModel:
        def predict(self, features):
            return np.zeros(features.shape[0])

        def predict_proba(self, features):
            return np.tile([0.5, 0.5], (features.shape[0], 1))

    pipe = InferencePipeline(config=InferenceConfig(enable_caching=True))
    pipe._get_model = lambda model_type, version, specific=None: FakeModel()

    req = InferenceRequest(model_type="direction", features=np.zeros((4, 3)))
    r1 = asyncio.run(pipe.predict(req))
    r2 = asyncio.run(pipe.predict(req))
    assert r1.cache_hit is False
    assert r2.cache_hit is True


__all__ = []
