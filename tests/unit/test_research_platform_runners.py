"""Tests for local-data evaluation runner reconstruction and worker integration."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from research.platform.data_catalog import DatasetManifest, LicenseStatus, ValueOrigin
from research.platform.domain import AlgorithmFamily, DataResolution, Market, ResearchTrack
from research.platform.experiments import ExperimentSpec
from research.platform.jobs import ResearchJobManager
from research.platform.runners import (
    ExistingStrategyJobRunner,
    _build_portfolio_config,
    experiment_spec_from_record,
)
from research.platform.storage import ExperimentStore


UTC = timezone.utc


def _spec(*, assumptions: bool = True) -> ExperimentSpec:
    # Fee, execution, strategy and sampling assumptions are fixed in the experiment hash.
    parameters = {
        "strategy_name": "absolute_momentum",
        "strategy_parameters": {"period": 10, "threshold": 0.0},
    }
    if assumptions:
        parameters["execution_assumptions"] = {
            "slippage_bps": 5,
            "impact_coefficient_bps": 10,
            "max_participation": 0.05,
            "max_gross_exposure": 1.0,
            "periods_per_year": 252,
        }
    return ExperimentSpec(
        experiment_id="runner-test-experiment",
        market=Market.NSE,
        track=ResearchTrack.NSE_INDIVIDUAL,
        algorithm_family=AlgorithmFamily.EXISTING_STRATEGY,
        resolution=DataResolution.ONE_DAY,
        dataset_ids=("runner-test-data-v1",),
        random_seed=37,
        git_commit="0123456789abcdef0123456789abcdef01234567",
        code_version="runner-test",
        training_start=datetime(2016, 1, 1, tzinfo=UTC),
        training_end=datetime(2018, 1, 1, tzinfo=UTC),
        validation_start=datetime(2018, 1, 1, tzinfo=UTC),
        validation_end=datetime(2020, 1, 1, tzinfo=UTC),
        oos_start=datetime(2020, 1, 1, tzinfo=UTC),
        oos_end=datetime(2022, 1, 1, tzinfo=UTC),
        final_holdout_start=datetime(2026, 10, 2, tzinfo=UTC),
        final_holdout_end=datetime(2026, 11, 8, tzinfo=UTC),
        cost_model_id="nse-delivery-cost-model",
        execution_model_id="next-open-participation-impact-v1",
        objectives=("net_return", "max_drawdown", "turnover"),
        parameters=parameters,
        created_at=datetime(2026, 11, 8, tzinfo=UTC),
    )


def _bars() -> dict[str, pd.DataFrame]:
    # Synthetic deterministic bars exercise the runner only; these are not market data.
    index = pd.date_range("2015-01-01", "2022-01-02", freq="D", tz="Asia/Kolkata")
    step = np.arange(len(index), dtype=np.float64)
    close = 100.0 + 0.015 * step + 3.0 * np.sin(step / 12.0)
    frame = pd.DataFrame(
        {
            "open": close - 0.05,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.full(len(index), 50000.0),
        },
        index=index,
    )
    return {"TEST": frame}


def _store(path: Path, spec: ExperimentSpec) -> ExperimentStore:
    # The manifest declares a synthetic source and an approved test-only licence.
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


def test_experiment_spec_record_round_trip_preserves_fingerprint(tmp_path) -> None:
    # Jobs reconstruct exactly the same experiment hash that the user created.
    spec = _spec()
    store = _store(tmp_path / "round-trip.sqlite3", spec)
    restored = experiment_spec_from_record(store.get_experiment(spec.experiment_id))
    assert restored.fingerprint == spec.fingerprint
    assert restored.parameters == spec.parameters
    assert restored.final_holdout_start == spec.final_holdout_start


def test_nse_default_runner_config_uses_fee_adapter_and_declared_execution_settings() -> None:
    # NSE delivery costs and execution model are independently fingerprinted.
    spec = _spec()
    manifest = {"exchange": "NSE", "market": "nse"}
    config, periods = _build_portfolio_config(spec, [manifest])
    assert config.market is Market.NSE
    assert config.fee_calculator is not None
    assert config.cost_model_id == spec.cost_model_id
    assert config.execution_model_id == spec.execution_model_id
    assert config.slippage_bps == 5
    assert periods == 252


def test_existing_strategy_job_runner_executes_and_persists_partition_results(tmp_path) -> None:
    # Inject deterministic test bars while retaining store, validation and accounting code.
    spec = _spec()
    store = _store(tmp_path / "runner.sqlite3", spec)
    manager = ResearchJobManager(store, max_workers=1, max_queued=1)
    runner = ExistingStrategyJobRunner(bar_loader=lambda current_store, current_spec: _bars())
    manager.register_runner("existing_strategy_evaluation", runner)
    try:
        job_id = manager.submit(spec.experiment_id, "existing_strategy_evaluation")
        job = manager.wait(job_id, timeout=20)
        assert job["status"] == "succeeded", job["error_message"]
        result = job["result"]
        assert result["final_holdout_accessed"] is False
        assert [item["partition"] for item in result["partitions"]] == [
            "train", "validation", "out_of_sample"
        ]
        assert store.candidates(spec.experiment_id)[0]["family"] == "existing_strategy"
        events = store.events(spec.experiment_id)
        assert any(event["event_type"] == "existing_strategy_evaluated" for event in events)
    finally:
        manager.shutdown(wait=True, cancel_pending=True)


def test_default_runner_rejects_missing_execution_assumptions(tmp_path) -> None:
    # Hidden fee/fill defaults are not allowed to leak into an experiment result.
    spec = _spec(assumptions=False)
    store = _store(tmp_path / "missing-assumptions.sqlite3", spec)
    manager = ResearchJobManager(store, max_workers=1, max_queued=1)
    runner = ExistingStrategyJobRunner(bar_loader=lambda current_store, current_spec: _bars())
    manager.register_runner("existing_strategy_evaluation", runner)
    try:
        job_id = manager.submit(spec.experiment_id, "existing_strategy_evaluation")
        job = manager.wait(job_id, timeout=5)
        assert job["status"] == "failed"
        assert "execution_assumptions" in job["error_message"]
    finally:
        manager.shutdown(wait=True, cancel_pending=True)
