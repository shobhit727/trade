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
    assert bars["BTCINR"]["close"].iloc[-1] == 8030000

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
    assert bars["BTCUSDT"]["open"].iloc[0] == 100000 * 83
    assert bars["BTCUSDT"]["open"].iloc[1] == 101000 * 84
    assert bars["BTCUSDT"].attrs["fx_alignment"] == "backward_asof_no_future"
