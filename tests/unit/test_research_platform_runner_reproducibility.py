"""Runner-level reproducibility metadata tests (audit F-023 / section 7.21)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from research.platform.data_catalog import DatasetManifest, LicenseStatus, ValueOrigin
from research.platform.domain import AlgorithmFamily, DataResolution, Market, ResearchTrack
from research.platform.experiments import ExperimentSpec
from research.platform.jobs import ResearchJobManager
from research.platform.runners import ExistingStrategyJobRunner
from research.platform.storage import ExperimentStore

UTC = timezone.utc


def _spec(*, seed: int = 37, experiment_id: str = "repro-runner-test") -> ExperimentSpec:
    return ExperimentSpec(
        experiment_id=experiment_id,
        market=Market.NSE,
        track=ResearchTrack.NSE_INDIVIDUAL,
        algorithm_family=AlgorithmFamily.EXISTING_STRATEGY,
        resolution=DataResolution.ONE_DAY,
        dataset_ids=("repro-test-data-v1",),
        random_seed=seed,
        git_commit="0123456789abcdef0123456789abcdef01234567",
        code_version="repro-runner-test",
        training_start=datetime(2016, 1, 1, tzinfo=UTC),
        training_end=datetime(2018, 1, 1, tzinfo=UTC),
        validation_start=datetime(2018, 1, 1, tzinfo=UTC),
        validation_end=datetime(2020, 1, 1, tzinfo=UTC),
        oos_start=datetime(2026, 10, 2, tzinfo=UTC),
        oos_end=datetime(2026, 10, 16, tzinfo=UTC),
        final_holdout_start=datetime(2026, 10, 16, tzinfo=UTC),
        final_holdout_end=datetime(2026, 11, 8, tzinfo=UTC),
        cost_model_id="nse-delivery-cost-model",
        execution_model_id="next-open-participation-impact-v1",
        objectives=("net_return", "max_drawdown", "turnover"),
        parameters={
            "strategy_name": "absolute_momentum",
            "strategy_parameters": {"period": 10, "threshold": 0.0},
            "execution_assumptions": {
                "slippage_bps": 5,
                "impact_coefficient_bps": 10,
                "max_participation": 0.05,
                "max_gross_exposure": 1.0,
                "periods_per_year": 252,
            },
        },
        created_at=datetime(2026, 11, 8, tzinfo=UTC),
    )


def _bars() -> dict[str, pd.DataFrame]:
    index = pd.date_range("2015-01-01", "2026-11-09", freq="D", tz="Asia/Kolkata")
    step = np.arange(len(index), dtype=np.float64)
    close = 100.0 + 0.015 * step + 3.0 * np.sin(step / 12.0)
    return {
        "TEST": pd.DataFrame(
            {
                "open": close - 0.05,
                "high": close + 0.5,
                "low": close - 0.5,
                "close": close,
                "volume": np.full(len(index), 50000.0),
            },
            index=index,
        )
    }


def _store(path: Path, spec: ExperimentSpec) -> ExperimentStore:
    store = ExperimentStore(path)
    store.create_experiment(spec)
    store.register_dataset(DatasetManifest(
        dataset_id=spec.dataset_ids[0],
        market=Market.NSE,
        provider="unit-test",
        source="synthetic-bars-not-market-data",
        instrument="TEST",
        exchange="NSE",
        category="ohlcv",
        resolution=DataResolution.ONE_DAY,
        coverage_start=datetime(2015, 1, 1, tzinfo=UTC),
        coverage_end=datetime(2026, 11, 9, tzinfo=UTC),
        timezone="Asia/Kolkata",
        timestamp_convention="synthetic-daily-bar-index",
        acquired_at=datetime(2026, 11, 8, tzinfo=UTC),
        update_frequency="daily",
        license_status=LicenseStatus.APPROVED,
        license_reference="synthetic-test-fixture-only",
        value_origin=ValueOrigin.OBSERVED,
        quality_score=1.0,
        processing_history=("generated inside unit test",),
    ))
    return store


def test_runner_persists_environment_record_and_returns_it(tmp_path) -> None:
    spec = _spec()
    store = _store(tmp_path / "repro.sqlite3", spec)
    manager = ResearchJobManager(store, max_workers=1, max_queued=1)
    runner = ExistingStrategyJobRunner(bar_loader=lambda current_store, current_spec: _bars())
    manager.register_runner("existing_strategy_evaluation", runner)
    try:
        job_id = manager.submit(spec.experiment_id, "existing_strategy_evaluation")
        job = manager.wait(job_id, timeout=30)
        assert job["status"] == "succeeded", job["error_message"]
        environment = job["result"]["environment"]
        # Every audit 7.21 dimension is inside the returned result bundle.
        assert environment["python"]["version"]
        assert environment["compute_backend"] == "numpy"
        assert environment["random_seed"] == spec.random_seed
        assert "uncommitted_diff" in environment["working_tree"]
        # The identical record is persisted as an immutable experiment event.
        events = store.events(spec.experiment_id)
        recorded = [e for e in events if e["event_type"] == "environment_recorded"]
        assert len(recorded) == 1
        assert recorded[0]["payload"] == environment
    finally:
        manager.shutdown(wait=True, cancel_pending=True)


def test_second_job_reproduce_check_passes_on_same_machine(tmp_path) -> None:
    spec = _spec(experiment_id="repro-runner-same-env")
    store = _store(tmp_path / "same-env.sqlite3", spec)
    manager = ResearchJobManager(store, max_workers=1, max_queued=1)
    runner = ExistingStrategyJobRunner(bar_loader=lambda current_store, current_spec: _bars())
    manager.register_runner("existing_strategy_evaluation", runner)
    try:
        first = manager.wait(manager.submit(spec.experiment_id, "existing_strategy_evaluation"), timeout=30)
        assert first["status"] == "succeeded", first["error_message"]
        # A repeat job on the same environment passes reproduce_check and succeeds.
        second = manager.wait(manager.submit(spec.experiment_id, "existing_strategy_evaluation"), timeout=30)
        assert second["status"] == "succeeded", second["error_message"]
        events = store.events(spec.experiment_id)
        recorded = [e for e in events if e["event_type"] == "environment_recorded"]
        assert len(recorded) == 2
    finally:
        manager.shutdown(wait=True, cancel_pending=True)


def test_runner_reproduce_check_rejects_drifted_recorded_environment(tmp_path) -> None:
    spec = _spec(experiment_id="repro-runner-drift")
    store = _store(tmp_path / "drift.sqlite3", spec)
    # A recorded environment claiming a different Python version cannot be
    # re-derived on this machine: reproduce_check must fail the job explicitly.
    drifted = {
        "record_version": "1",
        "python": {"version": "3.0.0", "implementation": "CPython", "executable": "/gone"},
        "os": {"system": "Linux", "release": "drift", "architecture": "x86_64"},
        "cpu_model": "drifted-cpu",
        "ram_total_bytes": 1,
        "gpu": {"model": None, "driver_version": None, "cuda_version": None, "available": False},
        "compute_backend": "numpy",
        "compute_fallback_reason": None,
        "packages": {"numpy": "0.0.1"},
        "working_tree": {"clean": None, "uncommitted_diff": None},
        "random_seed": spec.random_seed,
        "numpy_random_state": {
            "bit_generator": "PCG64",
            "state": {"state": 1, "inc": 1},
            "has_uint32": 0,
            "uinteger": 0,
        },
        "precision_mode": "float64",
        "thread_count": 1,
        "resource_use": {"max_rss_kb": None},
        "timezone": "UTC",
        "timezone_rules": "UTC",
        "captured_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
    }
    store.append_event(spec.experiment_id, "environment_recorded", drifted)
    manager = ResearchJobManager(store, max_workers=1, max_queued=1)
    runner = ExistingStrategyJobRunner(bar_loader=lambda current_store, current_spec: _bars())
    manager.register_runner("existing_strategy_evaluation", runner)
    try:
        job_id = manager.submit(spec.experiment_id, "existing_strategy_evaluation")
        job = manager.wait(job_id, timeout=30)
        assert job["status"] == "failed"
        assert "reproducibility check failed" in job["error_message"]
        assert "python.version" in job["error_message"]
    finally:
        manager.shutdown(wait=True, cancel_pending=True)
