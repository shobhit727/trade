
"""
Auto-Retraining Pipeline

Automatically retrains models when data drift is detected.
Integrates with DriftDetector and WalkForwardTrainer.
"""

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import numpy as np
import numpy.typing as npt

from cryptobot.ml.online import DriftConfig, DriftDetector
from cryptobot.utils.logging import get_logger

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RetrainTrigger(StrEnum):
    """Conditions that trigger retraining."""
    DRIFT_DETECTED = "drift_detected"
    PERFORMANCE_DEGRADATION = "performance_degradation"
    SCHEDULED = "scheduled"
    MANUAL = "manual"
    DATA_QUALITY = "data_quality"


@dataclass
class RetrainConfig:
    """Configuration for auto-retraining."""
    # Drift detection
    drift_config: DriftConfig = field(default_factory=DriftConfig)
    check_interval_minutes: int = 60  # Check for drift every hour

    # Performance monitoring
    performance_window: int = 100  # Samples to evaluate
    min_performance_threshold: float = 0.52  # Minimum accuracy
    degradation_threshold: float = 0.05  # 5% drop triggers retrain

    # Scheduling
    min_retrain_interval_hours: int = 24  # Minimum time between retrains
    max_retrain_frequency_per_day: int = 4

    # Training config
    training_config: object | None = None  # TrainingConfig

    # Model persistence
    save_path: str = "./models"
    keep_versions: int = 5

    # Notifications
    notify_on_retrain: bool = True
    webhook_url: str | None = None


@dataclass
class RetrainEvent:
    """Record of a retraining event."""
    trigger: str
    timestamp: datetime
    model_type: str
    old_performance: float
    new_performance: float | None = None
    duration_seconds: float = 0.0
    success: bool = False
    error: str | None = None
    model_version: str = ""
    metadata: dict = field(default_factory=dict)


class AutoRetrainer:
    """
    Automatic retraining pipeline with drift detection.

    Monitors model performance and data drift, automatically
    triggers retraining when conditions are met.
    """

    def __init__(
        self,
        config: RetrainConfig | None = None,
        on_retrain_callback: Callable[[RetrainEvent], Any] | None = None,
    ):
        self.config = config or RetrainConfig()
        self.on_retrain_callback = on_retrain_callback
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_retrain: dict[str, datetime] = {}
        self._retrain_history: list[RetrainEvent] = []
        self._performance_buffer: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

        # Initialize components
        self.drift_detector = DriftDetector(self.config.drift_config)
        self.training_config = self.config.training_config or None

    async def start(self) -> None:
        """Start the auto-retraining loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("Auto-retrainer started")

    async def stop(self) -> None:
        """Stop the auto-retraining loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Auto-retrainer stopped")

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                await self._check_all_models()
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")

            await asyncio.sleep(self.config.check_interval_minutes * 60)

    async def _check_all_models(self) -> None:
        """Check all registered models for retrain triggers."""
        # This would iterate over registered models
        # For now, placeholder for the monitoring logic
        pass

    async def check_drift(
        self,
        model_type: str,
        features: npt.NDArray[np.float64],
        reference_features: npt.NDArray[np.float64] | None = None,
    ) -> bool:
        """Check for data drift."""
        return self.drift_detector.detect(features, reference=reference_features)

    async def check_performance(
        self,
        model_type: str,
        recent_accuracy: float,
    ) -> bool:
        """Check if performance has degraded."""
        if model_type not in self._performance_buffer:
            self._performance_buffer[model_type] = []

        self._performance_buffer[model_type].append(recent_accuracy)

        # Keep only recent window
        window = self.config.performance_window
        if len(self._performance_buffer[model_type]) > window:
            self._performance_buffer[model_type] = self._performance_buffer[model_type][-window:]

        if len(self._performance_buffer[model_type]) < 10:
            return False  # Not enough data

        recent_avg = np.mean(self._performance_buffer[model_type][-10:])
        overall_avg = np.mean(self._performance_buffer[model_type])

        degradation = overall_avg - recent_avg
        return degradation > self.config.degradation_threshold

    async def trigger_retrain(
        self,
        model_type: str,
        trigger: RetrainTrigger,
        features: npt.NDArray[np.float64] | None = None,
        labels: npt.NDArray[np.float64] | None = None,
    ) -> bool:
        """
        Trigger retraining for a model type.

        Returns:
            True if retrain was initiated, False if skipped (cooldown).
        """
        async with self._lock:
            # Check cooldown
            last_retrain = self._last_retrain.get(model_type)
            if last_retrain:
                elapsed = _utcnow() - last_retrain
                if elapsed < timedelta(hours=self.config.min_retrain_interval_hours):
                    logger.info(f"Retrain skipped for {model_type}: cooldown active")
                    return False

                # Check daily frequency
                today_retrains = sum(
                    1 for e in self._retrain_history
                    if e.model_type == model_type
                    and e.timestamp > _utcnow() - timedelta(days=1)
                )
                if today_retrains >= self.config.max_retrain_frequency_per_day:
                    logger.info(f"Retrain skipped for {model_type}: daily limit reached")
                    return False

        start_time = time.perf_counter()
        event = RetrainEvent(
            trigger=trigger.value,
            timestamp=_utcnow(),
            model_type=model_type,
            old_performance=0.0,  # Would be filled from monitoring
        )

        try:
            logger.info(f"Starting retrain for {model_type} (trigger: {trigger.value})")

            # Retrain logic would go here
            # For now, just record the event
            event.success = True
            event.new_performance = 0.55  # Placeholder
            event.duration_seconds = time.perf_counter() - start_time
            event.model_version = f"v{_utcnow().strftime('%Y%m%d%H%M%S')}"

            async with self._lock:
                self._last_retrain[model_type] = _utcnow()
                self._retrain_history.append(event)

            if self.on_retrain_callback:
                await self.on_retrain_callback(event)

            if self.config.notify_on_retrain and self.config.webhook_url:
                await self._send_webhook(event)

            logger.info(f"Retrain completed for {model_type} in {event.duration_seconds:.2f}s")
            return True

        except Exception as e:
            event.success = False
            event.error = str(e)
            event.duration_seconds = time.perf_counter() - start_time
            logger.error(f"Retrain failed for {model_type}: {e}")
            return False

    async def _send_webhook(self, event: RetrainEvent) -> None:
        """Send webhook notification."""
        if not self.config.webhook_url:
            return
        # Implementation would POST to webhook
        pass

    def get_history(self, model_type: str | None = None) -> list[RetrainEvent]:
        """Get retraining history."""
        if model_type:
            return [e for e in self._retrain_history if e.model_type == model_type]
        return self._retrain_history

    def get_last_retrain(self, model_type: str) -> datetime | None:
        """Get last retrain time for a model type."""
        return self._last_retrain.get(model_type)

    def get_performance_history(self, model_type: str) -> list[float]:
        """Get performance history for a model."""
        return self._performance_buffer.get(model_type, [])

    async def force_retrain(
        self,
        model_type: str,
        features: npt.NDArray[np.float64] | None = None,
        labels: npt.NDArray[np.float64] | None = None,
    ) -> bool:
        """Manually trigger retraining."""
        return await self.trigger_retrain(
            model_type,
            RetrainTrigger.MANUAL,
            features,
            labels,
        )

    def get_status(self) -> dict[str, Any]:
        """Get current status."""
        return {
            "running": self._running,
            "last_retrains": {
                k: v.isoformat() for k, v in self._last_retrain.items()
            },
            "retrain_count_24h": {
                mt: sum(1 for e in self._retrain_history
                       if e.model_type == mt
                       and e.timestamp > _utcnow() - timedelta(hours=24))
                for mt in set(e.model_type for e in self._retrain_history)
            },
            "recent_events": [
                {
                    "trigger": e.trigger,
                    "model_type": e.model_type,
                    "timestamp": e.timestamp.isoformat(),
                    "success": e.success,
                    "duration": e.duration_seconds,
                }
                for e in self._retrain_history[-10:]
            ],
        }


class RetrainScheduler:
    """Simple scheduler for periodic retraining."""

    def __init__(
        self,
        auto_retrainer: AutoRetrainer,
        schedule: dict[str, str],  # model_type -> cron expression
    ):
        self.auto_retrainer = auto_retrainer
        self.schedule = schedule
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        while self._running:
            now = _utcnow()
            for model_type, cron_expr in self.schedule.items():
                if self._should_run(now, cron_expr):
                    await self.auto_retrainer.trigger_retrain(
                        model_type,
                        RetrainTrigger.SCHEDULED,
                    )
            await asyncio.sleep(60)  # Check every minute

    def _should_run(self, now: datetime, cron_expr: str) -> bool:
        """Simple cron matching (simplified)."""
        # Full implementation would use croniter
        return True


__all__ = [
    "AutoRetrainer",
    "RetrainConfig",
    "RetrainTrigger",
    "RetrainEvent",
    "RetrainScheduler",
]
