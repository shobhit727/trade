"""Tests for the existing-strategy track-aware evaluation runner."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from research.platform.data_catalog import DatasetManifest, LicenseStatus, ValueOrigin
from research.platform.domain import AlgorithmFamily, DataResolution, Market, ResearchTrack
from research.platform.experiments import ExperimentSpec
from research.platform.evaluation import evaluate_existing_strategy
from research.platform.portfolio import PortfolioConfig
from research.platform.storage import ExperimentStore


UTC = timezone.utc


def _experiment() -> ExperimentSpec:
    # Windows remain chronological; the old NSE TEST window is not reused as holdout.
    return ExperimentSpec(
        experiment_id="eval-absolute-momentum-001",
        market=Market.NSE,
        track=ResearchTrack.NSE_INDIVIDUAL,
        algorithm_family=AlgorithmFamily.EXISTING_STRATEGY,
        resolution=DataResolution.ONE_DAY,
        dataset_ids=("synthetic-nse-eod",),
        random_seed=42,
        git_commit="0123456789abcdef0123456789abcdef01234567",
        code_version="evaluation-test",
        training_start=datetime(2016, 1, 1, tzinfo=UTC),
        training_end=datetime(2018, 1, 1, tzinfo=UTC),
        validation_start=datetime(2018, 1, 1, tzinfo=UTC),
        validation_end=datetime(2020, 1, 1, tzinfo=UTC),
        oos_start=datetime(2026, 10, 2, tzinfo=UTC),
        oos_end=datetime(2026, 10, 16, tzinfo=UTC),
        final_holdout_start=datetime(2026, 10, 16, tzinfo=UTC),
        final_holdout_end=datetime(2026, 11, 8, tzinfo=UTC),
        cost_model_id="nse-test-cost-v1",
        execution_model_id="next-open-test-v1",
        objectives=("net_return", "max_drawdown"),
        parameters={
            "strategy_name": "absolute_momentum",
            "strategy_parameters": {"period": 10, "threshold": 0.0},
        },
        created_at=datetime(2026, 11, 8, tzinfo=UTC),
    )


def _bars() -> dict[str, pd.DataFrame]:
    # Use sufficient pre-window history so indicators can warm up before TRAIN begins.
    index = pd.date_range("2015-01-01", "2026-11-09", freq="D", tz="Asia/Kolkata")
    steps = np.arange(len(index), dtype=np.float64)
    close = 100.0 + 0.01 * steps + 2.0 * np.sin(steps / 11.0)
    frame = pd.DataFrame(
        {
            "open": close - 0.05,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.full(len(index), 100000.0),
        },
        index=index,
    )
    return {"TEST": frame}


def _registered_store(path, spec: ExperimentSpec) -> ExperimentStore:
    # The persisted dataset manifest covers all experiment windows but remains synthetic.
    store = ExperimentStore(path)
    store.create_experiment(spec)
    store.register_dataset(DatasetManifest(
        dataset_id="synthetic-nse-eod",
        market=Market.NSE,
        provider="unit-test",
        source="synthetic-bars-only",
        instrument="TEST",
        exchange="NSE",
        category="ohlcv",
        resolution=DataResolution.ONE_DAY,
        coverage_start=datetime(2015, 1, 1, tzinfo=UTC),
        coverage_end=datetime(2026, 11, 9, tzinfo=UTC),
        timezone="Asia/Kolkata",
        timestamp_convention="bar-close-time",
        acquired_at=datetime(2026, 11, 8, tzinfo=UTC),
        update_frequency="daily",
        license_status=LicenseStatus.APPROVED,
        license_reference="synthetic-test-only",
        value_origin=ValueOrigin.OBSERVED,
        quality_score=1.0,
        processing_history=("synthetic test fixture",),
    ))
    return store


def test_existing_strategy_runner_evaluates_three_stages_without_holdout(tmp_path) -> None:
    # The same strategy candidate is evaluated with a fresh capital ledger for each stage.
    spec = _experiment()
    store = _registered_store(tmp_path / "experiment.sqlite3", spec)
    config = PortfolioConfig(
        market=Market.NSE,
        fee_bps=Decimal("0"),
        slippage_bps=Decimal("1"),
        impact_coefficient_bps=Decimal("1"),
        max_participation=Decimal("0.05"),
        max_gross_exposure=Decimal("1.0"),
        assumed_timezone="Asia/Kolkata",
        cost_model_id=spec.cost_model_id,
        execution_model_id=spec.execution_model_id,
    )
    result = evaluate_existing_strategy(
        spec,
        _bars(),
        config,
        periods_per_year=252,
        store=store,
    )
    assert [item.partition for item in result.evaluations] == [
        "train", "validation", "out_of_sample"
    ]
    assert result.final_holdout_accessed is False
    assert all(item.metrics["observations"] > 0 for item in result.evaluations)
    assert all(item.result.market is Market.NSE for item in result.evaluations)
    assert store.candidates(spec.experiment_id)[0]["family"] == "existing_strategy"
    assert store.events(spec.experiment_id)[0]["event_type"] == "existing_strategy_evaluated"


def test_existing_strategy_runner_requires_matching_cost_model_and_track_scope() -> None:
    # Market- and cost-specific accounting cannot be changed by the strategy parameters.
    spec = _experiment()
    wrong_cost = PortfolioConfig(
        market=Market.NSE,
        fee_bps=Decimal("0"),
        cost_model_id="different-cost-model",
    )
    with pytest.raises(ValueError, match="cost model id"):
        evaluate_existing_strategy(spec, _bars(), wrong_cost, periods_per_year=252)

    wrong_market = PortfolioConfig(
        market=Market.CRYPTO,
        fee_bps=Decimal("0"),
        cost_model_id=spec.cost_model_id,
        execution_model_id=spec.execution_model_id,
    )
    with pytest.raises(ValueError, match="market"):
        evaluate_existing_strategy(spec, _bars(), wrong_market, periods_per_year=252)


def test_existing_strategy_runner_refuses_multi_symbol_individual_track(tmp_path) -> None:
    # An individual-asset experiment cannot accidentally turn into a portfolio.
    spec = _experiment()
    bars = _bars()
    bars["SECOND"] = bars["TEST"].copy()
    config = PortfolioConfig(
        market=Market.NSE,
        fee_bps=Decimal("0"),
        cost_model_id=spec.cost_model_id,
        execution_model_id=spec.execution_model_id,
    )
    store = _registered_store(tmp_path / "multi-symbol.sqlite3", spec)
    with pytest.raises(ValueError, match="bar symbols must exactly match registered dataset instruments"):
        evaluate_existing_strategy(
            spec, bars, config, periods_per_year=252, store=store
        )


def test_existing_strategy_runner_requires_matching_execution_model(tmp_path) -> None:
    # The fill assumptions are part of the immutable experiment identity.
    spec = _experiment()
    config = PortfolioConfig(
        market=Market.NSE,
        fee_bps=Decimal("0"),
        cost_model_id=spec.cost_model_id,
        execution_model_id="different-fill-model",
    )
    with pytest.raises(ValueError, match="execution model id"):
        evaluate_existing_strategy(
            spec,
            _bars(),
            config,
            periods_per_year=252,
            store=_registered_store(tmp_path / "execution-mismatch.sqlite3", spec),
        )


def test_existing_strategy_runner_rejects_unregistered_extra_bar_symbols(tmp_path) -> None:
    # Every portfolio asset must resolve to one registered, approved dataset manifest.
    spec = _experiment()
    bars = _bars()
    bars["UNREGISTERED"] = bars["TEST"].copy()
    store = _registered_store(tmp_path / "unregistered-bars.sqlite3", spec)
    config = PortfolioConfig(
        market=Market.NSE,
        fee_bps=Decimal("0"),
        cost_model_id=spec.cost_model_id,
        execution_model_id=spec.execution_model_id,
    )
    with pytest.raises(ValueError, match="exactly match registered dataset instruments"):
        evaluate_existing_strategy(
            spec, bars, config, periods_per_year=252, store=store
        )


# --- F-001 / CR-001: versioned OOS acceptance policy -------------------------

from research.platform.classification import OOS_ACCEPTANCE_POLICY_V1


def test_existing_strategy_evaluation_without_policy_records_unknown(tmp_path) -> None:
    # Without an approved policy the stored record must keep the OOS pass unknown.
    spec = _experiment()
    store = _registered_store(tmp_path / "no-policy.sqlite3", spec)
    config = PortfolioConfig(
        market=Market.NSE,
        fee_bps=Decimal("0"),
        slippage_bps=Decimal("1"),
        impact_coefficient_bps=Decimal("1"),
        max_participation=Decimal("0.05"),
        max_gross_exposure=Decimal("1.0"),
        assumed_timezone="Asia/Kolkata",
        cost_model_id=spec.cost_model_id,
        execution_model_id=spec.execution_model_id,
    )
    result = evaluate_existing_strategy(spec, _bars(), config, periods_per_year=252, store=store)
    assert result.oos_policy_version is None

    record = result.to_dict()["oos_acceptance"]
    assert record["outcome"] == "unknown"
    assert record["policy_version"] is None
    assert record["reasons"]
    assert record is not None  # stored record is fully materialised, not a stub

    persisted = [
        event for event in store.events(spec.experiment_id)
        if event["event_type"] == "existing_strategy_evaluated"
    ]
    assert len(persisted) == 1
    payload = persisted[0]["payload"]
    assert payload["oos_acceptance"]["outcome"] == "unknown"
    assert payload["oos_policy_version"] is None
    assert payload["classification_evidence"]["oos_passed"] is None
    # The existing-strategy evaluator never performs model selection, so the
    # classification stays training-only; the OOS verdict itself is unknown.
    assert payload["classification"] == "training_only"


def test_existing_strategy_evaluation_with_policy_classifies_verdict(tmp_path) -> None:
    # The approved policy stamps its version and classifies the OOS partition.
    spec = _experiment()
    store = _registered_store(tmp_path / "with-policy.sqlite3", spec)
    config = PortfolioConfig(
        market=Market.NSE,
        fee_bps=Decimal("0"),
        slippage_bps=Decimal("1"),
        impact_coefficient_bps=Decimal("1"),
        max_participation=Decimal("0.05"),
        max_gross_exposure=Decimal("1.0"),
        assumed_timezone="Asia/Kolkata",
        cost_model_id=spec.cost_model_id,
        execution_model_id=spec.execution_model_id,
    )
    result = evaluate_existing_strategy(
        spec,
        _bars(),
        config,
        periods_per_year=252,
        store=store,
        oos_policy_version=OOS_ACCEPTANCE_POLICY_V1.policy_version,
    )
    assert result.oos_policy_version == "v1-2026-11-10"

    acceptance = result.oos_acceptance()
    assert acceptance["policy_version"] == "v1-2026-11-10"
    assert acceptance["outcome"] in {"pass", "fail"}
    # The stored classification must agree with the classified verdict.
    evidence = result.to_dict()["classification_evidence"]
    if acceptance["outcome"] == "pass":
        assert evidence["oos_passed"] is True
    else:
        assert acceptance["reasons"]
        assert evidence["oos_passed"] is False

    persisted = [
        event for event in store.events(spec.experiment_id)
        if event["event_type"] == "existing_strategy_evaluated"
    ][-1]["payload"]
    assert persisted["oos_policy_version"] == "v1-2026-11-10"
    assert persisted["oos_acceptance"]["outcome"] == acceptance["outcome"]
    assert persisted["classification_evidence"]["oos_passed"] == evidence["oos_passed"]


def test_existing_strategy_evaluation_rejects_unapproved_policy_version(tmp_path) -> None:
    # A candidate-record version that was never approved cannot silently pass.
    spec = _experiment()
    store = _registered_store(tmp_path / "mismatch.sqlite3", spec)
    config = PortfolioConfig(
        market=Market.NSE,
        fee_bps=Decimal("0"),
        slippage_bps=Decimal("1"),
        impact_coefficient_bps=Decimal("1"),
        max_participation=Decimal("0.05"),
        max_gross_exposure=Decimal("1.0"),
        assumed_timezone="Asia/Kolkata",
        cost_model_id=spec.cost_model_id,
        execution_model_id=spec.execution_model_id,
    )
    with pytest.raises(ValueError, match="not an approved OOS acceptance policy"):
        evaluate_existing_strategy(
            spec,
            _bars(),
            config,
            periods_per_year=252,
            store=store,
            oos_policy_version="v0-never-approved",
        )


def test_existing_strategy_evaluation_repeat_run_is_idempotent_for_candidates(tmp_path) -> None:
    # A repeated OOS call appends a new immutable evaluation event, never a second candidate.
    spec = _experiment()
    store = _registered_store(tmp_path / "repeat.sqlite3", spec)
    config = PortfolioConfig(
        market=Market.NSE,
        fee_bps=Decimal("0"),
        slippage_bps=Decimal("1"),
        impact_coefficient_bps=Decimal("1"),
        max_participation=Decimal("0.05"),
        max_gross_exposure=Decimal("1.0"),
        assumed_timezone="Asia/Kolkata",
        cost_model_id=spec.cost_model_id,
        execution_model_id=spec.execution_model_id,
    )
    policy = OOS_ACCEPTANCE_POLICY_V1.policy_version
    first = evaluate_existing_strategy(
        spec, _bars(), config, periods_per_year=252, store=store, oos_policy_version=policy
    )
    second = evaluate_existing_strategy(
        spec, _bars(), config, periods_per_year=252, store=store, oos_policy_version=policy
    )
    assert len(store.candidates(spec.experiment_id)) == 1
    assert first.oos_acceptance() == second.oos_acceptance()

    evaluations = [
        event for event in store.events(spec.experiment_id)
        if event["event_type"] == "existing_strategy_evaluated"
    ]
    assert len(evaluations) == 2
    assert [item["payload"]["repeat_evaluation"] for item in evaluations] == [False, True]
    assert evaluations[1]["payload"]["oos_acceptance"] == first.oos_acceptance()


def test_oos_metrics_extracts_only_the_oos_partition(tmp_path) -> None:
    # The acceptance gate reads the declared OOS partition, never train or validation.
    spec = _experiment()
    store = _registered_store(tmp_path / "partition.sqlite3", spec)
    config = PortfolioConfig(
        market=Market.NSE,
        fee_bps=Decimal("0"),
        slippage_bps=Decimal("1"),
        impact_coefficient_bps=Decimal("1"),
        max_participation=Decimal("0.05"),
        max_gross_exposure=Decimal("1.0"),
        assumed_timezone="Asia/Kolkata",
        cost_model_id=spec.cost_model_id,
        execution_model_id=spec.execution_model_id,
    )
    result = evaluate_existing_strategy(
        spec, _bars(), config, periods_per_year=252, store=store,
        oos_policy_version=OOS_ACCEPTANCE_POLICY_V1.policy_version,
    )
    oos = next(item for item in result.evaluations if item.partition == "out_of_sample")
    assert result.oos_metrics() == dict(oos.metrics)
