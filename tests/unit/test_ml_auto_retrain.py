from __future__ import annotations

from datetime import UTC, datetime

from cryptobot.ml.auto_retrain import (
    AutoRetrainer,
    RetrainConfig,
    RetrainEvent,
    RetrainTrigger,
)


def test_retrain_config_defaults():
    cfg = RetrainConfig()
    assert cfg.check_interval_minutes == 60
    assert cfg.performance_window == 100
    assert cfg.min_retrain_interval_hours == 24
    assert cfg.max_retrain_frequency_per_day == 4


def test_retrain_trigger_enum():
    assert RetrainTrigger.DRIFT_DETECTED.value == "drift_detected"
    assert RetrainTrigger.PERFORMANCE_DEGRADATION.value == "performance_degradation"
    assert RetrainTrigger.SCHEDULED.value == "scheduled"
    assert RetrainTrigger.MANUAL.value == "manual"
    assert RetrainTrigger.DATA_QUALITY.value == "data_quality"


def test_retrain_event_creation():
    ts = datetime.now(UTC)
    e = RetrainEvent(
        trigger="drift_detected",
        timestamp=ts,
        model_type="direction",
        old_performance=0.55,
    )
    assert e.trigger == "drift_detected"
    assert e.model_type == "direction"
    assert e.success is False
    assert e.duration_seconds == 0.0


def test_auto_retrainer_init():
    ar = AutoRetrainer()
    assert ar._running is False
    assert ar._task is None
    assert ar.config.check_interval_minutes == 60


def test_auto_retrainer_with_custom_config():
    cfg = RetrainConfig(check_interval_minutes=30, min_retrain_interval_hours=12)
    ar = AutoRetrainer(config=cfg)
    assert ar.config.check_interval_minutes == 30
    assert ar.config.min_retrain_interval_hours == 12


def test_auto_retrainer_get_history_empty():
    ar = AutoRetrainer()
    assert ar.get_history() == []
    assert ar.get_history("direction") == []


def test_auto_retrainer_get_last_retrain_none():
    ar = AutoRetrainer()
    assert ar.get_last_retrain("direction") is None


def test_auto_retrainer_get_performance_history_empty():
    ar = AutoRetrainer()
    assert ar.get_performance_history("direction") == []


def test_auto_retrainer_get_status():
    ar = AutoRetrainer()
    status = ar.get_status()
    assert status["running"] is False
    assert status["last_retrains"] == {}
    assert status["retrain_count_24h"] == {}
    assert status["recent_events"] == []


__all__ = []
