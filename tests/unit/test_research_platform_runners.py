"""Tests for local-data evaluation runner reconstruction and worker integration."""

from __future__ import annotations

from dataclasses import replace
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
    ExistingStrategyOptimizerJobRunner,
    GeneticProgrammingJobRunner,
    NeuroevolutionJobRunner,
    ParetoStrategySearchJobRunner,
    StrategyCompositionJobRunner,
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
        oos_start=datetime(2026, 10, 2, tzinfo=UTC),
        oos_end=datetime(2026, 10, 16, tzinfo=UTC),
        final_holdout_start=datetime(2026, 10, 16, tzinfo=UTC),
        final_holdout_end=datetime(2026, 11, 8, tzinfo=UTC),
        cost_model_id="nse-delivery-cost-model",
        execution_model_id="next-open-participation-impact-v1",
        objectives=("net_return", "max_drawdown", "turnover"),
        parameters=parameters,
        created_at=datetime(2026, 11, 8, tzinfo=UTC),
    )


def _bars() -> dict[str, pd.DataFrame]:
    # Synthetic deterministic bars exercise the runner only; these are not market data.
    index = pd.date_range("2015-01-01", "2026-11-09", freq="D", tz="Asia/Kolkata")
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

        # Re-running the identical frozen spec appends an evaluation event, not a duplicate row.
        second_job_id = manager.submit(spec.experiment_id, "existing_strategy_evaluation")
        second_job = manager.wait(second_job_id, timeout=20)
        assert second_job["status"] == "succeeded", second_job["error_message"]
        assert len(store.candidates(spec.experiment_id)) == 1

        events = store.events(spec.experiment_id)
        evaluations = [event for event in events if event["event_type"] == "existing_strategy_evaluated"]
        assert len(evaluations) == 2
        assert evaluations[1]["payload"]["repeat_evaluation"] is True
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



def _crypto_spec(dataset_id: str) -> ExperimentSpec:
    # Crypto experiment has its own INR seed capital and one spot dataset.
    return ExperimentSpec(
        experiment_id="runner-crypto-data-test",
        market=Market.CRYPTO,
        track=ResearchTrack.CRYPTO_INDIVIDUAL,
        algorithm_family=AlgorithmFamily.EXISTING_STRATEGY,
        resolution=DataResolution.ONE_HOUR,
        dataset_ids=(dataset_id,),
        random_seed=13,
        git_commit="0123456789abcdef0123456789abcdef01234567",
        code_version="crypto-loader-test",
        training_start=datetime(2025, 1, 1, tzinfo=UTC),
        training_end=datetime(2025, 1, 1, 1, tzinfo=UTC),
        validation_start=datetime(2025, 1, 1, 1, tzinfo=UTC),
        validation_end=datetime(2025, 1, 1, 2, tzinfo=UTC),
        oos_start=datetime(2025, 1, 1, 2, tzinfo=UTC),
        oos_end=datetime(2025, 1, 1, 3, tzinfo=UTC),
        final_holdout_start=datetime(2025, 1, 1, 3, tzinfo=UTC),
        final_holdout_end=datetime(2025, 1, 1, 4, tzinfo=UTC),
        cost_model_id="crypto-binance-taker-maker1-taker5",
        execution_model_id="next-open-participation-impact-v1",
        objectives=("net_return", "max_drawdown"),
        parameters={
            "strategy_name": "absolute_momentum",
            "execution_assumptions": {
                "slippage_bps": 5,
                "impact_coefficient_bps": 10,
                "max_participation": 0.02,
                "max_gross_exposure": 1.0,
                "periods_per_year": 365 * 24,
            },
            "fee_schedule": {"maker_fee_bps": 1, "taker_fee_bps": 5},
        },
        created_at=datetime(2026, 11, 8, tzinfo=UTC),
    )


def _write_crypto_csv(path: Path, *, timestamps: list[int], close: list[float]) -> str:
    # Write a small deterministic OHLCV file and return the exact source checksum.
    import hashlib

    path.parent.mkdir(parents=True, exist_ok=True)
    rows = ["timestamp,open,high,low,close,volume"]
    for stamp, price in zip(timestamps, close, strict=True):
        rows.append(f"{stamp},{price},{price * 1.01},{price * 0.99},{price},1000")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_crypto_loader_verifies_registered_source_hash_and_quote_currency(tmp_path) -> None:
    # INR-quoted crypto spot bars are loaded only when file bytes match the manifest.
    from research.platform.runners import load_registered_bars

    exchange = tmp_path / "binance"
    stamps = [
        int(pd.Timestamp("2025-01-01T00:00:00Z").timestamp() * 1000),
        int(pd.Timestamp("2025-01-01T01:00:00Z").timestamp() * 1000),
        int(pd.Timestamp("2025-01-01T02:00:00Z").timestamp() * 1000),
        int(pd.Timestamp("2025-01-01T03:00:00Z").timestamp() * 1000),
    ]
    source = exchange / "BTCINR_1h.csv"
    digest = _write_crypto_csv(source, timestamps=stamps, close=[8000000, 8010000, 8020000, 8030000])
    spec = _crypto_spec("crypto-binance-btcinr-1h")
    store = ExperimentStore(tmp_path / "crypto.sqlite3")
    store.create_experiment(spec)
    store.register_dataset(DatasetManifest(
        dataset_id=spec.dataset_ids[0],
        market=Market.CRYPTO,
        provider="unit-test",
        source="binance/BTCINR_1h.csv",
        instrument="BTCINR",
        exchange="binance",
        category="ohlcv",
        resolution=DataResolution.ONE_HOUR,
        coverage_start=datetime(2025, 1, 1, tzinfo=UTC),
        coverage_end=datetime(2025, 1, 1, 3, tzinfo=UTC),
        timezone="UTC",
        timestamp_convention="bar_open",
        acquired_at=datetime(2026, 11, 8, tzinfo=UTC),
        update_frequency="hourly",
        license_status=LicenseStatus.APPROVED,
        license_reference="synthetic-test-only",
        value_origin=ValueOrigin.OBSERVED,
        extra_metadata={
            "file_sha256": digest,
            "numeric_timestamp_unit": "ms",
            "quote_currency": "INR",
            "timestamp_position": "bar_open",
        },
    ))
    bars = load_registered_bars(store, spec, crypto_data_root=tmp_path)
    assert list(bars) == ["BTCINR"]
    assert bars["BTCINR"]["close"].iloc[-1] == 8020000
    assert (bars["BTCINR"].index < spec.oos_end).all()

    # A changed local file cannot silently reuse a stale provenance manifest.
    source.write_text(source.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    try:
        load_registered_bars(store, spec, crypto_data_root=tmp_path)
    except ValueError as exc:
        assert "checksum mismatch" in str(exc)
    else:
        raise AssertionError("modified crypto source was accepted")


def test_crypto_loader_converts_usdt_using_prior_fx_close_only(tmp_path) -> None:
    # The FX close at 01:00 is the first rate available to the 01:00 crypto bar open.
    from research.platform.runners import load_registered_bars

    exchange = tmp_path / "binance"
    asset_stamps = [
        int(pd.Timestamp(f"2025-01-01T{hour:02d}:00:00Z").timestamp() * 1000)
        for hour in range(4)
    ]
    fx_stamps = [
        int(pd.Timestamp("2024-12-31T23:00:00Z").timestamp() * 1000),
        *asset_stamps[:-1],
    ]
    asset_path = exchange / "BTCUSDT_1h.csv"
    asset_hash = _write_crypto_csv(
        asset_path, timestamps=asset_stamps, close=[100000, 101000, 102000, 103000]
    )
    fx_path = exchange / "USDTINR_1h.csv"
    fx_hash = _write_crypto_csv(fx_path, timestamps=fx_stamps, close=[83, 84, 85, 86])

    spec = _crypto_spec("crypto-binance-btcusdt-1h")
    store = ExperimentStore(tmp_path / "fx.sqlite3")
    store.create_experiment(spec)
    store.register_dataset(DatasetManifest(
        dataset_id=spec.dataset_ids[0],
        market=Market.CRYPTO,
        provider="unit-test",
        source="binance/BTCUSDT_1h.csv",
        instrument="BTCUSDT",
        exchange="binance",
        category="ohlcv",
        resolution=DataResolution.ONE_HOUR,
        coverage_start=datetime(2025, 1, 1, tzinfo=UTC),
        coverage_end=datetime(2025, 1, 1, 3, tzinfo=UTC),
        timezone="UTC",
        timestamp_convention="bar_open",
        acquired_at=datetime(2026, 11, 8, tzinfo=UTC),
        update_frequency="hourly",
        license_status=LicenseStatus.APPROVED,
        license_reference="synthetic-test-only",
        value_origin=ValueOrigin.OBSERVED,
        extra_metadata={
            "file_sha256": asset_hash,
            "numeric_timestamp_unit": "ms",
            "quote_currency": "USDT",
            "timestamp_position": "bar_open",
            "fx_dataset_id": "fx-usdt-inr-v1",
            "max_fx_staleness_seconds": 7200,
        },
    ))
    store.register_dataset(DatasetManifest(
        dataset_id="fx-usdt-inr-v1",
        market=Market.CRYPTO,
        provider="unit-test",
        source="binance/USDTINR_1h.csv",
        instrument="USDTINR",
        exchange="binance",
        category="fx",
        resolution=DataResolution.ONE_HOUR,
        coverage_start=datetime(2025, 1, 1, tzinfo=UTC),
        coverage_end=datetime(2025, 1, 1, 3, tzinfo=UTC),
        timezone="UTC",
        timestamp_convention="bar_open",
        acquired_at=datetime(2026, 11, 8, tzinfo=UTC),
        update_frequency="hourly",
        license_status=LicenseStatus.APPROVED,
        license_reference="synthetic-test-only",
        value_origin=ValueOrigin.OBSERVED,
        extra_metadata={
            "file_sha256": fx_hash,
            "numeric_timestamp_unit": "ms",
            "quote_currency": "INR",
            "timestamp_position": "bar_open",
            "base_currency": "USDT",
        },
    ))

    bars = load_registered_bars(store, spec, crypto_data_root=tmp_path)
    # Each bar uses the close of the immediately preceding completed FX candle.
    assert bars["BTCUSDT"].index[0] == pd.Timestamp("2025-01-01T00:00:00Z")
    assert len(bars["BTCUSDT"]) == 3
    assert (bars["BTCUSDT"].index < spec.oos_end).all()
    assert bars["BTCUSDT"]["open"].iloc[0] == 100000 * 83
    assert bars["BTCUSDT"]["open"].iloc[1] == 101000 * 84
    assert bars["BTCUSDT"].attrs["fx_alignment"] == "backward_asof_no_future"



def test_existing_strategy_optimizer_searches_train_selects_validation_then_evaluates_oos(tmp_path) -> None:
    # A small fixed-seed search demonstrates the full no-holdout optimization sequence.
    base = _spec()
    optimizer_parameters = dict(base.parameters)
    optimizer_parameters["optimization"] = {
        "budget": 6,
        "validation_candidates": 2,
        "objective": "sharpe",
    }
    spec = replace(
        base,
        experiment_id="runner-existing-strategy-random-search",
        algorithm_family=AlgorithmFamily.RANDOM_SEARCH,
        parameters=optimizer_parameters,
    )
    store = _store(tmp_path / "optimizer-runner.sqlite3", spec)
    manager = ResearchJobManager(store, max_workers=1, max_queued=1)
    runner = ExistingStrategyOptimizerJobRunner(
        bar_loader=lambda current_store, current_spec: _bars()
    )
    manager.register_runner("existing_strategy_optimization", runner)
    try:
        job_id = manager.submit(spec.experiment_id, "existing_strategy_optimization")
        job = manager.wait(job_id, timeout=60)
        assert job["status"] == "succeeded", job["error_message"]
        result = job["result"]
        assert result["search_family"] == "random_search"
        assert result["search_method"] == "random"
        assert result["candidate_count"] >= 3
        assert result["successful_train_candidates"] == 6
        assert len(result["validation_shortlist"]) == 2
        assert result["selected_candidate"]["validation_score"] is not None
        assert result["final_holdout_accessed"] is False
        assert result["final_evaluation"]["final_holdout_accessed"] is False
        assert [row["partition"] for row in result["final_evaluation"]["partitions"]] == [
            "train", "validation", "out_of_sample"
        ]
        stored_candidates = store.candidates(spec.experiment_id)
        families = {candidate["family"] for candidate in stored_candidates}
        assert "random_search" in families
        search_candidates = [
            candidate for candidate in stored_candidates
            if candidate["family"] == "random_search"
        ]
        validation_candidates = [
            candidate for candidate in stored_candidates
            if candidate["family"] == "random_search_validation"
        ]
        selected_validation = next(
            candidate for candidate in validation_candidates
            if candidate["candidate_id"] == result["selected_candidate"]["candidate_id"]
        )
        assert selected_validation["lineage"]["origin"] == "validation_shortlist"
        assert selected_validation["lineage"]["parent_candidate_ids"]
        oos_candidates = [
            candidate for candidate in stored_candidates
            if candidate["family"] == "random_search_selected_oos"
        ]
        assert len(oos_candidates) == 1
        assert oos_candidates[0]["lineage"]["parent_candidate_ids"] == [
            selected_validation["candidate_id"]
        ]
        assert search_candidates
        assert all(
            candidate["lineage"]["operator"] == "random"
            and candidate["lineage"]["origin"] == "existing_strategy_parameter_search"
            for candidate in search_candidates
        )
        assert result["total_train_evaluations"] == result["budget"] + 2
        assert result["successful_train_candidates"] == result["budget"]
        assert any(
            event["event_type"] == "existing_strategy_optimization_selected"
            for event in store.events(spec.experiment_id)
        )
    finally:
        manager.shutdown(wait=True, cancel_pending=True)


def test_optimizer_runner_rejects_unsupported_or_missing_search_settings(tmp_path) -> None:
    # The experiment must explicitly identify a supported method and a finite budget.
    base = _spec()
    bad_parameters = dict(base.parameters)
    bad_parameters["optimization"] = {"budget": 8}
    spec = replace(
        base,
        experiment_id="runner-invalid-optimizer-spec",
        algorithm_family=AlgorithmFamily.GRID_SEARCH,
        parameters=bad_parameters,
    )
    store = _store(tmp_path / "invalid-optimizer.sqlite3", spec)
    manager = ResearchJobManager(store, max_workers=1, max_queued=1)
    runner = ExistingStrategyOptimizerJobRunner(
        bar_loader=lambda current_store, current_spec: _bars()
    )
    manager.register_runner("existing_strategy_optimization", runner)
    try:
        job_id = manager.submit(spec.experiment_id, "existing_strategy_optimization")
        job = manager.wait(job_id, timeout=10)
        assert job["status"] == "failed"
        assert "validation_candidates" in job["error_message"]
    finally:
        manager.shutdown(wait=True, cancel_pending=True)



def test_differential_evolution_optimizer_persists_resolvable_parent_lineage(tmp_path) -> None:
    # DE must persist each attempted genome and resolve offspring parent IDs to stored rows.
    base = _spec()
    optimizer_parameters = dict(base.parameters)
    optimizer_parameters["optimization"] = {
        "budget": 8,
        "validation_candidates": 2,
        "objective": "sharpe",
        "population_size": 4,
        "generations": 1,
        "mutation": 0.7,
        "crossover": 0.8,
    }
    spec = replace(
        base,
        experiment_id="runner-existing-strategy-differential-evolution",
        algorithm_family=AlgorithmFamily.DIFFERENTIAL_EVOLUTION,
        parameters=optimizer_parameters,
    )
    store = _store(tmp_path / "de-runner.sqlite3", spec)
    manager = ResearchJobManager(store, max_workers=1, max_queued=1)
    runner = ExistingStrategyOptimizerJobRunner(
        bar_loader=lambda current_store, current_spec: _bars()
    )
    manager.register_runner("existing_strategy_optimization", runner)
    try:
        job_id = manager.submit(spec.experiment_id, "existing_strategy_optimization")
        job = manager.wait(job_id, timeout=60)
        assert job["status"] == "succeeded", job["error_message"]
        result = job["result"]
        assert result["search_method"] == "differential_evolution"
        assert result["search_attempted_candidates"] == 8
        assert result["successful_train_candidates"] <= 8
        stored = store.candidates(spec.experiment_id)
        de_rows = [row for row in stored if row["family"] == "differential_evolution"]
        assert len(de_rows) == 8
        candidate_ids = {row["candidate_id"] for row in de_rows}
        offspring = [
            row for row in de_rows
            if row["lineage"].get("operator") == "differential_mutation_binomial_crossover"
        ]
        assert offspring
        assert all(row["lineage"].get("accepted") in {True, False} for row in offspring)
        for row in offspring:
            parent_ids = row["lineage"]["parent_candidate_ids"]
            assert len(parent_ids) == 4
            assert set(parent_ids).issubset(candidate_ids)

        selected_validation = next(
            row for row in stored
            if row["candidate_id"] == result["selected_candidate"]["candidate_id"]
        )
        selected_oos = next(
            row for row in stored
            if row["family"] == "differential_evolution_selected_oos"
        )
        assert selected_validation["lineage"]["parent_candidate_ids"]
        assert selected_oos["lineage"]["parent_candidate_ids"] == [
            selected_validation["candidate_id"]
        ]
        assert result["final_holdout_accessed"] is False
    finally:
        manager.shutdown(wait=True, cancel_pending=True)



def test_genetic_programming_worker_persists_lineage_selects_validation_and_evaluates_oos(tmp_path) -> None:
    # The small GP population exercises the complete train-freeze-OOS lifecycle.
    base = _spec()
    parameters = dict(base.parameters)
    parameters["genetic_programming"] = {
        "population_size": 4,
        "generations": 1,
        "max_depth": 3,
        "max_nodes": 15,
        "mutation_rate": 0.25,
        "validation_candidates": 2,
        "objective": "sharpe",
        "feature_windows": [3],
    }
    spec = replace(
        base,
        experiment_id="runner-genetic-programming",
        algorithm_family=AlgorithmFamily.GENETIC_PROGRAMMING,
        parameters=parameters,
    )
    store = _store(tmp_path / "gp-runner.sqlite3", spec)
    manager = ResearchJobManager(store, max_workers=1, max_queued=1)
    runner = GeneticProgrammingJobRunner(
        bar_loader=lambda current_store, current_spec: _bars()
    )
    manager.register_runner("genetic_programming", runner)
    try:
        job_id = manager.submit(spec.experiment_id, "genetic_programming")
        job = manager.wait(job_id, timeout=60)
        assert job["status"] == "succeeded", job["error_message"]
        result = job["result"]
        assert result["algorithm_family"] == "genetic_programming"
        assert result["candidate_count"] == 8
        assert result["successful_train_candidates"] > 0
        assert len(result["validation_shortlist"]) == 2
        assert result["out_of_sample"]["sample_count"] > 0
        assert result["final_holdout_accessed"] is False

        candidates = store.candidates(spec.experiment_id)
        train_candidates = [
            item for item in candidates if item["family"] == "genetic_programming"
        ]
        validation_candidates = [
            item for item in candidates if item["family"] == "genetic_programming_validation"
        ]
        oos_candidates = [
            item for item in candidates if item["family"] == "genetic_programming_selected_oos"
        ]
        assert len(train_candidates) == 8
        assert len(validation_candidates) == 2
        assert len(oos_candidates) == 1
        assert result["out_of_sample_candidate_id"] == oos_candidates[0]["candidate_id"]
        assert any(
            item["lineage"]["operator"] == "subtree_crossover"
            or item["lineage"]["operator"] == "subtree_crossover_then_mutation"
            for item in train_candidates
        )
        candidate_ids = {item["candidate_id"] for item in candidates}
        for item in candidates:
            for parent_id in item["lineage"]["parent_candidate_ids"]:
                assert parent_id in candidate_ids
        selected_validation = next(
            item for item in validation_candidates
            if item["candidate_id"] == result["selected_candidate"]["validation_candidate_id"]
        )
        assert selected_validation["lineage"]["parent_candidate_ids"] == [
            result["selected_candidate"]["candidate_id"]
        ]
        assert oos_candidates[0]["lineage"]["parent_candidate_ids"] == [
            selected_validation["candidate_id"]
        ]
        event_types = {event["event_type"] for event in store.events(spec.experiment_id)}
        assert "genetic_programming_candidate_frozen" in event_types
        assert "genetic_programming_oos_recorded" in event_types
    finally:
        manager.shutdown(wait=True, cancel_pending=True)


def test_genetic_programming_worker_rejects_missing_model_settings(tmp_path) -> None:
    # A GP experiment cannot fall back to arbitrary population or feature-window defaults.
    base = _spec()
    parameters = dict(base.parameters)
    parameters["genetic_programming"] = {"population_size": 8}
    spec = replace(
        base,
        experiment_id="runner-genetic-programming-invalid",
        algorithm_family=AlgorithmFamily.GENETIC_PROGRAMMING,
        parameters=parameters,
    )
    store = _store(tmp_path / "gp-invalid.sqlite3", spec)
    manager = ResearchJobManager(store, max_workers=1, max_queued=1)
    runner = GeneticProgrammingJobRunner(
        bar_loader=lambda current_store, current_spec: _bars()
    )
    manager.register_runner("genetic_programming", runner)
    try:
        job_id = manager.submit(spec.experiment_id, "genetic_programming")
        job = manager.wait(job_id, timeout=10)
        assert job["status"] == "failed"
        assert "genetic_programming requires" in job["error_message"]
    finally:
        manager.shutdown(wait=True, cancel_pending=True)



def test_neuroevolution_worker_persists_mirrored_candidates_and_evaluates_oos(tmp_path) -> None:
    # A small dense model tests the complete neural TRAIN/VALIDATION/OOS lifecycle.
    base = _spec()
    parameters = dict(base.parameters)
    parameters["neuroevolution"] = {
        "hidden_size": 3,
        "population_size": 4,
        "generations": 2,
        "learning_rate": 0.05,
        "noise_std": 0.1,
        "weight_limit": 2.0,
        "validation_candidates": 2,
        "objective": "sharpe",
        "feature_windows": [3],
    }
    spec = replace(
        base,
        experiment_id="runner-neuroevolution",
        algorithm_family=AlgorithmFamily.NEUROEVOLUTION,
        parameters=parameters,
    )
    store = _store(tmp_path / "neuro-runner.sqlite3", spec)
    manager = ResearchJobManager(store, max_workers=1, max_queued=1)
    runner = NeuroevolutionJobRunner(
        bar_loader=lambda current_store, current_spec: _bars()
    )
    manager.register_runner("neuroevolution", runner)
    try:
        job_id = manager.submit(spec.experiment_id, "neuroevolution")
        job = manager.wait(job_id, timeout=60)
        assert job["status"] == "succeeded", job["error_message"]
        result = job["result"]
        assert result["algorithm_family"] == "neuroevolution"
        assert result["candidate_count"] == 8
        assert result["successful_train_candidates"] > 0
        assert len(result["validation_shortlist"]) == 2
        assert result["network"]["parameter_count"] > 0
        assert result["out_of_sample"]["sample_count"] > 0
        assert result["final_holdout_accessed"] is False

        candidates = store.candidates(spec.experiment_id)
        assert len(candidates) == 8
        assert all(item["family"] == "neuroevolution" for item in candidates)
        assert all(len(item["parameters"]["weights"]) == result["network"]["parameter_count"]
                   for item in candidates)
        candidate_ids = {item["candidate_id"] for item in candidates}
        later_generation = [item for item in candidates if item["generation"] == 1]
        assert later_generation
        assert all(item["lineage"]["parent_candidate_ids"] for item in later_generation)
        for item in later_generation:
            assert set(item["lineage"]["parent_candidate_ids"]).issubset(candidate_ids)
        event_types = {event["event_type"] for event in store.events(spec.experiment_id)}
        assert "neuroevolution_candidate_frozen" in event_types
        assert "neuroevolution_oos_recorded" in event_types
    finally:
        manager.shutdown(wait=True, cancel_pending=True)


def test_neuroevolution_worker_rejects_odd_or_unbounded_population(tmp_path) -> None:
    # The antithetic ES population must be even and remain within the fixed evaluation cap.
    base = _spec()
    parameters = dict(base.parameters)
    parameters["neuroevolution"] = {
        "hidden_size": 3,
        "population_size": 5,
        "generations": 2,
        "learning_rate": 0.05,
        "noise_std": 0.1,
        "weight_limit": 2.0,
        "validation_candidates": 2,
        "objective": "sharpe",
        "feature_windows": [3],
    }
    spec = replace(
        base,
        experiment_id="runner-neuroevolution-invalid",
        algorithm_family=AlgorithmFamily.NEUROEVOLUTION,
        parameters=parameters,
    )
    store = _store(tmp_path / "neuro-invalid.sqlite3", spec)
    manager = ResearchJobManager(store, max_workers=1, max_queued=1)
    runner = NeuroevolutionJobRunner(
        bar_loader=lambda current_store, current_spec: _bars()
    )
    manager.register_runner("neuroevolution", runner)
    try:
        job_id = manager.submit(spec.experiment_id, "neuroevolution")
        job = manager.wait(job_id, timeout=10)
        assert job["status"] == "failed"
        assert "population_size must be even" in job["error_message"]
    finally:
        manager.shutdown(wait=True, cancel_pending=True)



def test_strategy_composition_worker_evolves_registered_components_and_evaluates_oos(tmp_path) -> None:
    # The composition worker can use only the local declarative feature-component catalogue.
    base = _spec()
    parameters = dict(base.parameters)
    parameters["strategy_composition"] = {
        "population_size": 4,
        "generations": 2,
        "max_components": 6,
        "mutation_rate": 0.25,
        "validation_candidates": 2,
        "objective": "sharpe",
        "feature_windows": [3],
    }
    spec = replace(
        base,
        experiment_id="runner-strategy-composition",
        algorithm_family=AlgorithmFamily.STRATEGY_COMPOSITION,
        parameters=parameters,
    )
    store = _store(tmp_path / "composition-runner.sqlite3", spec)
    manager = ResearchJobManager(store, max_workers=1, max_queued=1)
    runner = StrategyCompositionJobRunner(
        bar_loader=lambda current_store, current_spec: _bars()
    )
    manager.register_runner("strategy_composition", runner)
    try:
        job_id = manager.submit(spec.experiment_id, "strategy_composition")
        job = manager.wait(job_id, timeout=60)
        assert job["status"] == "succeeded", job["error_message"]
        result = job["result"]
        assert result["algorithm_family"] == "strategy_composition"
        assert result["candidate_count"] == 12
        assert result["successful_train_candidates"] > 0
        assert len(result["validation_shortlist"]) == 2
        assert result["registry_component_count"] >= 6
        assert result["out_of_sample"]["sample_count"] > 0
        assert result["final_holdout_accessed"] is False

        candidates = store.candidates(spec.experiment_id)
        assert len(candidates) == 12
        assert all(item["family"] == "strategy_composition" for item in candidates)
        candidate_ids = {item["candidate_id"] for item in candidates}
        for item in candidates:
            assert item["parameters"]["composition"]
            for parent_id in item["lineage"]["parent_candidate_ids"]:
                assert parent_id in candidate_ids
        event_types = {event["event_type"] for event in store.events(spec.experiment_id)}
        assert "strategy_composition_candidate_frozen" in event_types
        assert "strategy_composition_oos_recorded" in event_types
    finally:
        manager.shutdown(wait=True, cancel_pending=True)


def test_strategy_composition_worker_rejects_missing_component_settings(tmp_path) -> None:
    # Population and feature defaults must be explicitly frozen in the experiment.
    base = _spec()
    parameters = dict(base.parameters)
    parameters["strategy_composition"] = {"population_size": 8}
    spec = replace(
        base,
        experiment_id="runner-composition-invalid",
        algorithm_family=AlgorithmFamily.STRATEGY_COMPOSITION,
        parameters=parameters,
    )
    store = _store(tmp_path / "composition-invalid.sqlite3", spec)
    manager = ResearchJobManager(store, max_workers=1, max_queued=1)
    runner = StrategyCompositionJobRunner(
        bar_loader=lambda current_store, current_spec: _bars()
    )
    manager.register_runner("strategy_composition", runner)
    try:
        job_id = manager.submit(spec.experiment_id, "strategy_composition")
        job = manager.wait(job_id, timeout=10)
        assert job["status"] == "failed"
        assert "strategy_composition requires settings" in job["error_message"]
    finally:
        manager.shutdown(wait=True, cancel_pending=True)



def test_pareto_search_worker_persists_nsga2_front_and_oos_evaluation(tmp_path) -> None:
    # A small NSGA-II run validates the multi-objective train/validation/frozen-OOS pipeline.
    base = _spec()
    parameters = dict(base.parameters)
    parameters["pareto_search"] = {
        "population_size": 4,
        "generations": 1,
        "mutation_rate": 0.25,
        "validation_candidates": 4,
        "objectives": ["cagr", "max_drawdown", "turnover"],
        "directions": ["max", "max", "min"],
    }
    spec = replace(
        base,
        experiment_id="runner-pareto-search",
        algorithm_family=AlgorithmFamily.PARETO_SEARCH,
        parameters=parameters,
    )
    store = _store(tmp_path / "pareto-runner.sqlite3", spec)
    manager = ResearchJobManager(store, max_workers=1, max_queued=1)
    runner = ParetoStrategySearchJobRunner(
        bar_loader=lambda current_store, current_spec: _bars()
    )
    manager.register_runner("pareto_search", runner)
    try:
        job_id = manager.submit(spec.experiment_id, "pareto_search")
        job = manager.wait(job_id, timeout=60)
        assert job["status"] == "succeeded", job["error_message"]
        result = job["result"]
        assert result["algorithm_family"] == "pareto_search"
        assert result["evaluations"] == 8
        assert result["candidate_count"] == 8
        assert result["objectives"] == ["cagr", "max_drawdown", "turnover"]
        assert result["directions"] == ["max", "max", "min"]
        assert result["train_pareto_front"]
        assert result["validation_shortlist"]
        assert result["selection_policy"] == "nsga2_crowding_within_validation_front"
        assert result["final_evaluation"]["final_holdout_accessed"] is False

        candidates = store.candidates(spec.experiment_id)
        assert len(candidates) == 8
        assert all(item["family"] == "pareto_search" for item in candidates)
        candidate_ids = {item["candidate_id"] for item in candidates}
        assert any(item["lineage"]["operator"] == "nsga2_crossover_mutation"
                   for item in candidates)
        for item in candidates:
            for parent_id in item["lineage"]["parent_candidate_ids"]:
                assert parent_id in candidate_ids
        assert any(
            event["event_type"] == "pareto_search_candidate_frozen"
            for event in store.events(spec.experiment_id)
        )
    finally:
        manager.shutdown(wait=True, cancel_pending=True)


def test_pareto_search_worker_rejects_single_objective_settings(tmp_path) -> None:
    # The multi-objective optimizer cannot silently degrade into a scalar search.
    base = _spec()
    parameters = dict(base.parameters)
    parameters["pareto_search"] = {
        "population_size": 4,
        "generations": 1,
        "mutation_rate": 0.25,
        "validation_candidates": 2,
        "objectives": ["cagr"],
        "directions": ["max"],
    }
    spec = replace(
        base,
        experiment_id="runner-pareto-invalid",
        algorithm_family=AlgorithmFamily.PARETO_SEARCH,
        parameters=parameters,
    )
    store = _store(tmp_path / "pareto-invalid.sqlite3", spec)
    manager = ResearchJobManager(store, max_workers=1, max_queued=1)
    runner = ParetoStrategySearchJobRunner(
        bar_loader=lambda current_store, current_spec: _bars()
    )
    manager.register_runner("pareto_search", runner)
    try:
        job_id = manager.submit(spec.experiment_id, "pareto_search")
        job = manager.wait(job_id, timeout=10)
        assert job["status"] == "failed"
        assert "2+ unique objectives" in job["error_message"]
    finally:
        manager.shutdown(wait=True, cancel_pending=True)



def test_hybrid_optimizer_ensembles_random_de_and_tpe_before_validation(tmp_path) -> None:
    # Three independently seeded optimizers share one TRAIN fitness and one VALIDATION freeze.
    base = _spec()
    parameters = dict(base.parameters)
    parameters["hybrid_optimization"] = {
        "methods": ["random_search", "differential_evolution", "bayesian"],
        "budget_per_method": 8,
        "validation_candidates": 4,
        "objective": "sharpe",
        "de_population_size": 4,
        "de_generations": 1,
        "de_mutation": 0.7,
        "de_crossover": 0.8,
        "tpe_startup_trials": 3,
    }
    spec = replace(
        base,
        experiment_id="runner-hybrid-optimizer",
        algorithm_family=AlgorithmFamily.HYBRID,
        parameters=parameters,
    )
    store = _store(tmp_path / "hybrid-optimizer.sqlite3", spec)
    manager = ResearchJobManager(store, max_workers=1, max_queued=1)
    runner = ExistingStrategyOptimizerJobRunner(
        bar_loader=lambda current_store, current_spec: _bars()
    )
    manager.register_runner("existing_strategy_optimization", runner)
    try:
        job_id = manager.submit(spec.experiment_id, "existing_strategy_optimization")
        job = manager.wait(job_id, timeout=90)
        assert job["status"] == "succeeded", job["error_message"]
        result = job["result"]
        assert result["search_family"] == "hybrid"
        assert result["search_method"] == "hybrid_ensemble"
        assert result["budget"] == 24
        assert result["search_attempted_candidates"] == 24
        assert result["total_train_evaluations"] == 26
        assert result["final_holdout_accessed"] is False
        assert result["final_evaluation"]["final_holdout_accessed"] is False

        candidates = store.candidates(spec.experiment_id)
        search_candidates = [
            item for item in candidates
            if item["family"] == "hybrid"
        ]
        assert search_candidates
        methods = {
            item["lineage"]["search_method"]
            for item in search_candidates
            if "search_method" in item["lineage"]
        }
        assert methods == {"random_search", "differential_evolution", "bayesian"}
        hybrid_de_candidates = [
            item for item in search_candidates
            if item["lineage"].get("search_method") == "differential_evolution"
            and item["lineage"].get("generation", 0) > 0
        ]
        assert hybrid_de_candidates
        stored_ids = {item["candidate_id"] for item in candidates}
        for item in hybrid_de_candidates:
            assert item["lineage"]["parent_candidate_ids"]
            assert set(item["lineage"]["parent_candidate_ids"]).issubset(stored_ids)
        assert result["validation_shortlist"]
        assert any(
            event["event_type"] == "existing_strategy_optimization_selected"
            for event in store.events(spec.experiment_id)
        )
    finally:
        manager.shutdown(wait=True, cancel_pending=True)


def test_hybrid_optimizer_rejects_incompatible_method_budget(tmp_path) -> None:
    # DE's population-generation product must exactly match the per-method budget.
    base = _spec()
    parameters = dict(base.parameters)
    parameters["hybrid_optimization"] = {
        "methods": ["random_search", "differential_evolution"],
        "budget_per_method": 8,
        "validation_candidates": 2,
        "objective": "sharpe",
        "de_population_size": 4,
        "de_generations": 2,
        "de_mutation": 0.7,
        "de_crossover": 0.8,
    }
    spec = replace(
        base,
        experiment_id="runner-hybrid-invalid-budget",
        algorithm_family=AlgorithmFamily.HYBRID,
        parameters=parameters,
    )
    store = _store(tmp_path / "hybrid-invalid.sqlite3", spec)
    manager = ResearchJobManager(store, max_workers=1, max_queued=1)
    runner = ExistingStrategyOptimizerJobRunner(
        bar_loader=lambda current_store, current_spec: _bars()
    )
    manager.register_runner("existing_strategy_optimization", runner)
    try:
        job_id = manager.submit(spec.experiment_id, "existing_strategy_optimization")
        job = manager.wait(job_id, timeout=10)
        assert job["status"] == "failed"
        assert "must equal" in job["error_message"]
    finally:
        manager.shutdown(wait=True, cancel_pending=True)



def test_hybrid_runner_merges_random_de_and_tpe_candidate_traces(tmp_path) -> None:
    # The search-method ensemble preserves every sub-search and merges them before validation.
    base = _spec()
    parameters = dict(base.parameters)
    parameters["hybrid_optimization"] = {
        "methods": ["random_search", "differential_evolution", "bayesian"],
        "budget_per_method": 8,
        "validation_candidates": 4,
        "objective": "sharpe",
        "de_population_size": 4,
        "de_generations": 1,
        "de_mutation": 0.7,
        "de_crossover": 0.8,
        "tpe_startup_trials": 3,
    }
    spec = replace(
        base,
        experiment_id="runner-hybrid-search",
        algorithm_family=AlgorithmFamily.HYBRID,
        parameters=parameters,
    )
    store = _store(tmp_path / "hybrid-runner.sqlite3", spec)
    manager = ResearchJobManager(store, max_workers=1, max_queued=1)
    runner = ExistingStrategyOptimizerJobRunner(
        bar_loader=lambda current_store, current_spec: _bars()
    )
    manager.register_runner("existing_strategy_optimization", runner)
    try:
        job_id = manager.submit(spec.experiment_id, "existing_strategy_optimization")
        job = manager.wait(job_id, timeout=90)
        assert job["status"] == "succeeded", job["error_message"]
        result = job["result"]
        assert result["search_family"] == "hybrid"
        assert result["search_method"] == "hybrid_ensemble"
        assert result["budget"] == 24
        assert result["search_attempted_candidates"] == 24
        assert result["successful_train_candidates"] == 24
        assert result["total_train_evaluations"] == 26
        assert result["final_holdout_accessed"] is False
        assert result["final_evaluation"]["final_holdout_accessed"] is False

        stored = store.candidates(spec.experiment_id)
        search_candidates = [item for item in stored if item["family"] == "hybrid"]
        methods = {
            item["lineage"]["search_method"]
            for item in search_candidates
        }
        assert methods == {"random_search", "differential_evolution", "bayesian"}
        de_offspring = [
            item for item in search_candidates
            if item["lineage"].get("search_method") == "differential_evolution"
            and item["lineage"].get("generation", 0) > 0
        ]
        assert de_offspring
        stored_ids = {item["candidate_id"] for item in stored}
        for item in de_offspring:
            assert item["lineage"]["parent_candidate_ids"]
            assert set(item["lineage"]["parent_candidate_ids"]).issubset(stored_ids)
        assert result["validation_shortlist"]
        assert any(
            event["event_type"] == "existing_strategy_optimization_selected"
            for event in store.events(spec.experiment_id)
        )
    finally:
        manager.shutdown(wait=True, cancel_pending=True)


def test_hybrid_runner_rejects_missing_method_or_incorrect_de_budget(tmp_path) -> None:
    # A hybrid run cannot hide a mismatched DE evaluation count behind another method.
    base = _spec()
    parameters = dict(base.parameters)
    parameters["hybrid_optimization"] = {
        "methods": ["random_search", "differential_evolution"],
        "budget_per_method": 8,
        "validation_candidates": 2,
        "objective": "sharpe",
        "de_population_size": 4,
        "de_generations": 2,
        "de_mutation": 0.7,
        "de_crossover": 0.8,
    }
    spec = replace(
        base,
        experiment_id="runner-hybrid-bad-de-budget",
        algorithm_family=AlgorithmFamily.HYBRID,
        parameters=parameters,
    )
    store = _store(tmp_path / "hybrid-invalid-runner.sqlite3", spec)
    manager = ResearchJobManager(store, max_workers=1, max_queued=1)
    runner = ExistingStrategyOptimizerJobRunner(
        bar_loader=lambda current_store, current_spec: _bars()
    )
    manager.register_runner("existing_strategy_optimization", runner)
    try:
        job_id = manager.submit(spec.experiment_id, "existing_strategy_optimization")
        job = manager.wait(job_id, timeout=10)
        assert job["status"] == "failed"
        assert "must equal" in job["error_message"]
    finally:
        manager.shutdown(wait=True, cancel_pending=True)
