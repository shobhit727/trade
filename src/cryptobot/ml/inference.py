
"""
Online Inference Pipeline

Provides production-ready inference with model versioning,
caching, and A/B testing support.
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import numpy as np
import numpy.typing as npt

from cryptobot.ml.features import FeatureSet
from cryptobot.utils.logging import get_logger

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class InferenceMode(StrEnum):
    """Inference mode."""
    SYNC = "sync"
    ASYNC = "async"
    BATCH = "batch"


class ModelVersion(StrEnum):
    """Model versioning strategy."""
    LATEST = "latest"
    STABLE = "stable"
    SPECIFIC = "specific"


@dataclass
class InferenceConfig:
    """Configuration for inference pipeline."""
    mode: InferenceMode = InferenceMode.SYNC
    model_version: ModelVersion = ModelVersion.LATEST
    specific_version: str | None = None
    cache_ttl_seconds: int = 60
    batch_size: int = 32
    max_latency_ms: float = 100.0
    enable_caching: bool = True
    enable_ab_testing: bool = False
    ab_test_split: float = 0.1  # 10% traffic to new model


@dataclass
class InferenceRequest:
    """Inference request."""
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=_utcnow)
    features: npt.NDArray[np.float64] | None = field(default=None)
    feature_set: FeatureSet | None = field(default=None)
    model_type: str = field(default="ensemble")
    version: ModelVersion = field(default=ModelVersion.LATEST)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class InferenceResponse:
    """Inference response."""
    request_id: str = field(default="")
    timestamp: datetime = field(default_factory=_utcnow)
    model_type: str = field(default="")
    version: str = field(default="")
    predictions: np.ndarray | None = field(default=None)
    probabilities: np.ndarray | None = field(default=None)
    confidence: np.ndarray | None = field(default=None)
    regime: int | None = field(default=None)
    volatility: float | None = field(default=None)
    latency_ms: float = field(default=0.0)
    cache_hit: bool = field(default=False)
    ab_test_group: str = field(default="control")


class ModelCache:
    """Thread-safe model cache with TTL."""

    def __init__(self, ttl_seconds: int = 60):
        self._cache: dict[str, tuple[Any, float]] = {}
        self.ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            if key in self._cache:
                value, timestamp = self._cache[key]
                if time.time() - timestamp < self.ttl_seconds:
                    return value
                else:
                    del self._cache[key]
        return None

    async def set(self, key: str, value: Any) -> None:
        async with self._lock:
            self._cache[key] = (value, time.time())

    async def clear(self) -> None:
        async with self._lock:
            self._cache.clear()


class ModelRegistry:
    """Model registry with versioning."""

    def __init__(self):
        self._models: dict[str, dict[str, Any]] = {}  # model_type -> {version: model}
        self._lock = asyncio.Lock()

    async def register(
        self,
        model_type: str,
        model: Any,
        version: str = "latest",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        async with self._lock:
            if model_type not in self._models:
                self._models[model_type] = {}
            self._models[model_type][version] = {
                "model": model,
                "registered_at": _utcnow(),
                "metadata": metadata or {},
            }
            logger.info(f"Registered {model_type} v{version}")

    async def get(
        self,
        model_type: str,
        version: ModelVersion = ModelVersion.LATEST,
        specific_version: str | None = None,
    ) -> Any | None:
        async with self._lock:
            if model_type not in self._models:
                return None

            versions = self._models[model_type]
            if not versions:
                return None

            if version == ModelVersion.SPECIFIC and specific_version:
                return versions.get(specific_version, {}).get("model")

            if version == ModelVersion.STABLE:
                # Return oldest (stable) version
                oldest = min(versions.keys(), key=lambda v: versions[v]["registered_at"])
                return versions[oldest]["model"]

            # Return latest
            latest = max(versions.keys(), key=lambda v: versions[v]["registered_at"])
            return versions[latest]["model"]

    async def list_versions(self, model_type: str) -> list[str]:
        async with self._lock:
            return list(self._models.get(model_type, {}).keys())


class InferencePipeline:
    """
    Production-ready inference pipeline with:
    - Model versioning and registry
    - Request/response caching
    - A/B testing support
    - Async/sync/batch modes
    - Latency monitoring
    """

    def __init__(
        self,
        config: InferenceConfig | None = None,
        registry: ModelRegistry | None = None,
        cache: ModelCache | None = None,
    ):
        self.config = config or InferenceConfig()
        self.registry = registry or ModelRegistry()
        self.cache = cache or ModelCache(self.config.cache_ttl_seconds)
        self._ab_test_counter = 0

        # Lazy-loaded models
        self._models: dict[str, Any] = {}

    async def initialize(self) -> None:
        """Initialize models from registry."""
        for model_type in ["direction", "volatility", "regime", "ensemble"]:
            for version in await self.registry.list_versions(model_type):
                model = await self.registry.get(model_type, ModelVersion.SPECIFIC, version)
                if model:
                    self._models[f"{model_type}:{version}"] = model

    def _get_model(self, model_type: str, version: ModelVersion, specific: str | None) -> Any:
        """Get model from cache or registry."""
        cache_key = f"{model_type}:{version.value}:{specific or 'latest'}"
        model = self._models.get(cache_key)
        if model is None:
            # Load from registry (simplified - in production would load from disk)
            pass
        return self._models.get(cache_key)

    def _select_ab_group(self) -> str:
        """Select A/B test group."""
        if not self.config.enable_ab_testing:
            return "control"
        # Simple hash-based assignment
        return "treatment" if (time.time() * 1000) % 100 < (self.config.ab_test_split * 100) else "control"

    def _cache_key(self, request: InferenceRequest) -> str | None:
        """Stable cache key for a request, or None when features are absent.

        The cache lookup and the cache store must use the *same* key, otherwise
        the cache can never hit (issue #48). The model version is part of the
        key so different versions are never conflated.
        """
        if request.features is None:
            return None
        return f"{request.model_type}:{request.version}:{hash(request.features.tobytes())}"

    async def predict(
        self,
        request: InferenceRequest,
    ) -> InferenceResponse:
        """Single prediction."""
        start_time = time.perf_counter()

        # Check cache
        cache_key = self._cache_key(request)
        if self.config.enable_caching and cache_key is not None:
            cached = await self.cache.get(cache_key)
            if cached:
                response = InferenceResponse(
                    request_id=request.request_id,
                    model_type=request.model_type,
                    version=request.version.value,
                    **cached,
                    cache_hit=True,
                    latency_ms=(time.perf_counter() - start_time) * 1000,
                )
                return response

        # Get model
        model = self._get_model(request.model_type, request.version, request.metadata.get("version"))

        if model is None:
            raise ValueError(f"Model {request.model_type} not available")

        # Prepare features
        if request.feature_set:
            features = request.feature_set.to_array()
        elif request.features is not None:
            features = request.features
        else:
            raise ValueError("No features provided")

        # Run inference
        time.perf_counter()
        if self.config.mode == InferenceMode.ASYNC:
            # Run in thread pool for CPU-bound models
            loop = asyncio.get_running_loop()
            predictions = await loop.run_in_executor(None, lambda: model.predict(features))
            probs = await loop.run_in_executor(None, lambda: model.predict_proba(features))
        else:
            predictions = model.predict(features)
            probs = model.predict_proba(features) if hasattr(model, 'predict_proba') else None

        # Build response
        response = InferenceResponse(
            request_id=request.request_id,
            model_type=request.model_type,
            version=request.version.value,
            predictions=predictions,
            probabilities=probs,
            latency_ms=(time.perf_counter() - start_time) * 1000,
            ab_test_group=self._select_ab_group(),
        )

        # Cache result
        cache_key = self._cache_key(request)
        if self.config.enable_caching and cache_key is not None:
            await self.cache.set(cache_key, {
                "predictions": predictions,
                "probabilities": probs,
                "regime": getattr(model, 'current_regime', lambda: None)() if hasattr(model, 'current_regime') else None,
                "volatility": None,
            })

        return response

    async def predict_batch(
        self,
        requests: list[InferenceRequest],
    ) -> list[InferenceResponse]:
        """Batch prediction."""
        if self.config.mode == InferenceMode.BATCH:
            # Process in batches
            batch_size = self.config.batch_size
            responses = []
            for i in range(0, len(requests), batch_size):
                batch = requests[i:i + self.config.batch_size]
                batch_responses = await asyncio.gather(*[self.predict(r) for r in batch])
                responses.extend(batch_responses)
            return responses
        else:
            return await asyncio.gather(*[self.predict(r) for r in requests])

    async def health_check(self) -> dict[str, Any]:
        """Health check for monitoring."""
        return {
            "status": "healthy",
            "models_loaded": len(self._models),
            "cache_size": len(self.cache._cache) if hasattr(self.cache, '_cache') else 0,
            "registry_models": {
                mt: len(versions) for mt, versions in self.registry._models.items()
            },
        }

    async def reload_models(self) -> None:
        """Hot-reload models from registry."""
        await self.initialize()
        logger.info("Models reloaded")


__all__ = [
    "InferenceConfig",
    "InferenceMode",
    "ModelVersion",
    "InferenceRequest",
    "InferenceResponse",
    "InferencePipeline",
    "ModelRegistry",
    "ModelCache",
    "ModelVersion",
    "InferenceMode",
]
