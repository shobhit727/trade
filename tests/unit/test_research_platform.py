"""Regression tests for the initial multi-market research foundation."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import numpy as np
import pytest

from research.platform.compute import ComputeEngine
from research.platform.data_catalog import (
    DataAvailabilityCatalog,
    DatasetManifest,
    LicenseStatus,
    TimeGap,
    ValueOrigin,
)
from research.platform.domain import AlgorithmFamily, DataResolution, Market, ResearchTrack
from research.platform.experiments import ExperimentSpec
from research.platform.market import Fill, MarketLedger, Side
from research.platform.storage import ExperimentStore
from research.platform.validation import (
    AccessRole,
    EvaluationState,
    Partition,
    SplitPlan,
    TimeWindow,
    ValidationLifecycle,
)


UTC = timezone.utc


def make_experiment(**overrides: object) -> ExperimentSpec:
    """Build a complete experiment fixture using non-overlapping UTC partitions."""
    # All dates are explicit so tests never depend on the machine's local timezone.
    values: dict[str, object] = {
        "experiment_id": "test-nse-gp-001",
        "market": Market.NSE,
        "track": ResearchTrack.NSE_INDIVIDUAL,
        "algorithm_family": AlgorithmFamily.GENETIC_PROGRAMMING,
        "resolution": DataResolution.ONE_DAY,
        "dataset_ids": ("nse-eod-v1",),
        "random_seed": 42,
        "git_commit": "0123456789abcdef0123456789abcdef01234567",
        "code_version": "test-build-1",
        "training_start": datetime(2016, 1, 1, tzinfo=UTC),
        "training_end": datetime(2020, 1, 1, tzinfo=UTC),
        "validation_start": datetime(2020, 1, 1, tzinfo=UTC),
        "validation_end": datetime(2022, 1, 1, tzinfo=UTC),
        "oos_start": datetime(2022, 1, 1, tzinfo=UTC),
        "oos_end": datetime(2024, 1, 1, tzinfo=UTC),
        "final_holdout_start": datetime(2026, 10, 2, tzinfo=UTC),
        "final_holdout_end": datetime(2026, 11, 8, tzinfo=UTC),
        "cost_model_id": "nse-delivery-costs-v1",
        "execution_model_id": "daily-close-next-open-v1",
        "objectives": ("net_return", "max_drawdown", "turnover"),
        "parameters": {"population_size": 64, "max_depth": 5},
        "created_at": datetime(2026, 11, 8, tzinfo=UTC),
    }
    values.update(overrides)
    return ExperimentSpec(**values)  # type: ignore[arg-type]


def make_manifest(**overrides: object) -> DatasetManifest:
    """Build a complete, licence-reviewed dataset manifest fixture."""
    # Provenance fields represent a synthetic test fixture, not a real data provider.
    values: dict[str, object] = {
        "dataset_id": "nse-eod-v1",
        "market": Market.NSE,
        "provider": "test-provider",
        "source": "synthetic-test-fixture",
        "instrument": "TEST",
        "exchange": "NSE",
        "category": "ohlcv",
        "resolution": DataResolution.ONE_DAY,
        "coverage_start": datetime(2016, 1, 1, tzinfo=UTC),
        "coverage_end": datetime(2026, 11, 9, tzinfo=UTC),
        "timezone": "Asia/Kolkata",
        "timestamp_convention": "bar-close-time",
        "acquired_at": datetime(2026, 11, 8, tzinfo=UTC),
        "update_frequency": "daily",
        "license_status": LicenseStatus.APPROVED,
        "license_reference": "test-only-licence-reference",
        "value_origin": ValueOrigin.OBSERVED,
        "quality_score": 0.99,
    }
    values.update(overrides)
    return DatasetManifest(**values)  # type: ignore[arg-type]


def make_fill(
    *,
    fill_id: str,
    market: Market = Market.NSE,
    side: Side = Side.BUY,
    quantity: Decimal = Decimal("1"),
    price: Decimal = Decimal("100"),
    fee: Decimal = Decimal("1"),
    instrument: str = "TEST",
) -> Fill:
    """Build an INR-normalised test fill with explicit assumptions."""
    # Production callers must populate FX and cost provenance from real data/models.
    return Fill(
        fill_id=fill_id,
        market=market,
        instrument=instrument,
        side=side,
        quantity=quantity,
        price_inr=price,
        fee_inr=fee,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        cost_model_id="test-cost-v1",
        fx_provenance="synthetic-test-fixture",
    )


def test_market_budgets_are_separate_and_market_fill_cannot_cross() -> None:
    """NSE and crypto receive separate ₹21L accounts with no cross-market fills."""
    # Each ledger is independently seeded from its own market specification.
    nse = MarketLedger(Market.NSE)
    crypto = MarketLedger(Market.CRYPTO)
    assert nse.cash_inr == Decimal("2100000.00")
    assert crypto.cash_inr == Decimal("2100000.00")

    with pytest.raises(ValueError, match="cross-market"):
        nse.apply_fill(make_fill(fill_id="crypto-fill", market=Market.CRYPTO))

    # Rejected fills do not debit the receiving market's cash or create positions.
    assert nse.cash_inr == Decimal("2100000.00")
    assert not nse._fill_ids
    assert not nse.positions


def test_market_ledger_accounting_and_duplicate_fill_guard() -> None:
    """Buy/sell accounting includes fees and prevents duplicate or uncovered fills."""
    # The ledger includes the buy fee in average entry and the sell fee in realised PnL.
    ledger = MarketLedger(Market.NSE)
    ledger.apply_fill(make_fill(fill_id="buy-1", quantity=Decimal("2")))
    assert ledger.cash_inr == Decimal("2099799.00")
    assert ledger.positions["TEST"].average_entry_inr == Decimal("100.5")

    ledger.apply_fill(
        make_fill(fill_id="sell-1", side=Side.SELL, quantity=Decimal("1"), price=Decimal("110"))
    )
    snapshot = ledger.snapshot({"TEST": Decimal("110")})
    assert snapshot.cash_inr == Decimal("2099908.00")
    assert snapshot.position_values_inr["TEST"] == Decimal("110")
    assert snapshot.equity_inr == Decimal("2100018.00")
    assert snapshot.realised_pnl_inr == Decimal("8.5")
    assert snapshot.fees_paid_inr == Decimal("2")

    with pytest.raises(ValueError, match="duplicate"):
        ledger.apply_fill(make_fill(fill_id="buy-1", quantity=Decimal("1")))
    with pytest.raises(ValueError, match="more than the existing"):
        ledger.apply_fill(make_fill(fill_id="oversell", side=Side.SELL, quantity=Decimal("5")))
    assert ledger.positions["TEST"].quantity == Decimal("1")
    assert "MISSING" not in ledger.positions
    with pytest.raises(ValueError, match="more than the existing"):
        ledger.apply_fill(make_fill(fill_id="sell-empty", side=Side.SELL, instrument="MISSING"))
    assert "MISSING" not in ledger.positions


def test_fill_rejects_naive_timestamp_and_invalid_fee() -> None:
    """Accounting cannot silently accept ambiguous event time or negative charges."""
    with pytest.raises(ValueError, match="timezone-aware"):
        make_fill(fill_id="naive").__class__(
            fill_id="naive", market=Market.NSE, instrument="TEST", side=Side.BUY,
            quantity=Decimal("1"), price_inr=Decimal("100"), fee_inr=Decimal("1"),
            timestamp=datetime(2026, 1, 1), cost_model_id="x",
        )
    with pytest.raises(ValueError, match="fee cannot be negative"):
        make_fill(fill_id="bad-fee", fee=Decimal("-1"))


def test_dataset_manifest_fingerprint_and_availability_filters() -> None:
    """Manifests retain source and resolution detail and reject silent ID replacement."""
    # Catalogued metadata is searchable by independent dimensions.
    catalog = DataAvailabilityCatalog([make_manifest()])
    manifest = catalog.get("nse-eod-v1")
    assert len(manifest.fingerprint) == 64
    assert catalog.query(market=Market.NSE, resolution=DataResolution.ONE_DAY) == (manifest,)
    assert catalog.query(market=Market.CRYPTO) == ()
    assert catalog.availability_matrix() == {"nse:NSE": {"1d": 1}}
    make_experiment().validate_datasets(catalog)

    crypto_catalog = DataAvailabilityCatalog([make_manifest(
        dataset_id="nse-eod-v1", market=Market.CRYPTO, exchange="TEST-EXCHANGE"
    )])
    with pytest.raises(ValueError, match="cross-market dataset"):
        make_experiment().validate_datasets(crypto_catalog)

    with pytest.raises(ValueError, match="different metadata"):
        catalog.register(make_manifest(quality_score=0.5))


def test_dataset_manifest_records_gaps_and_requires_timezone_aware_times() -> None:
    """Missing periods and timestamp origins are explicit, never silently interpolated."""
    gap = TimeGap(
        datetime(2020, 3, 1, tzinfo=UTC),
        datetime(2020, 3, 5, tzinfo=UTC),
        "provider outage",
    )
    manifest = make_manifest(known_gaps=(gap,), value_origin=ValueOrigin.OBSERVED)
    assert manifest.to_dict()["known_gaps"][0]["reason"] == "provider outage"
    with pytest.raises(ValueError, match="timezone-aware"):
        TimeGap(datetime(2020, 1, 1), datetime(2020, 1, 2, tzinfo=UTC), "naive start")
    with pytest.raises(ValueError, match="timezone-aware"):
        make_manifest(coverage_start=datetime(2016, 1, 1))


def test_experiment_fingerprint_binds_market_data_seed_and_cost_assumptions() -> None:
    """Different seeds or costs generate different experiment fingerprints."""
    # Canonical JSON fingerprint captures all experiment-defining fields.
    base = make_experiment()
    assert base.fingerprint != make_experiment(random_seed=43).fingerprint
    assert base.fingerprint != make_experiment(cost_model_id="nse-delivery-costs-v2").fingerprint
    assert base.fingerprint != make_experiment(dataset_ids=("nse-eod-v2",)).fingerprint
    assert base.fingerprint != make_experiment(compute_backend="cupy", compute_device="RTX-test").fingerprint

    with pytest.raises(ValueError, match="does not belong"):
        make_experiment(market=Market.CRYPTO)
    with pytest.raises(ValueError, match="chronological"):
        make_experiment(validation_start=datetime(2019, 1, 1, tzinfo=UTC))
    with pytest.raises(ValueError, match="JSON-compatible"):
        make_experiment(parameters={"bad": float("nan")})


def test_split_plan_enforces_chronology_and_embargo() -> None:
    """Split boundaries cannot overlap or violate the declared embargo."""
    # All adjacent windows use half-open endpoints and a two-day embargo.
    plan = SplitPlan(
        train=TimeWindow(datetime(2010, 1, 1, tzinfo=UTC), datetime(2018, 1, 1, tzinfo=UTC)),
        validation=TimeWindow(datetime(2018, 1, 3, tzinfo=UTC), datetime(2020, 1, 1, tzinfo=UTC)),
        oos=TimeWindow(datetime(2020, 1, 3, tzinfo=UTC), datetime(2022, 1, 1, tzinfo=UTC)),
        final_holdout=TimeWindow(datetime(2022, 1, 3, tzinfo=UTC), datetime(2024, 1, 1, tzinfo=UTC)),
        embargo=timedelta(days=2),
    )
    assert plan.protocol_id == "chronological-v1"
    with pytest.raises(ValueError, match="embargo"):
        SplitPlan(
            train=plan.train,
            validation=TimeWindow(datetime(2018, 1, 2, tzinfo=UTC), datetime(2020, 1, 1, tzinfo=UTC)),
            oos=plan.oos,
            final_holdout=plan.final_holdout,
            embargo=timedelta(days=2),
        )


def test_validation_lifecycle_blocks_leakage_and_opens_holdout_once() -> None:
    """Optimisation, OOS and final holdout access follow a one-way state machine."""
    # Discovery cannot inspect validation or OOS data; selection gets validation only.
    lifecycle = ValidationLifecycle()
    lifecycle.authorize(AccessRole.OPTIMIZER, Partition.TRAIN)
    lifecycle.authorize(AccessRole.MODEL_SELECTOR, Partition.VALIDATION)
    with pytest.raises(PermissionError):
        lifecycle.authorize(AccessRole.OPTIMIZER, Partition.VALIDATION)
    with pytest.raises(PermissionError):
        lifecycle.authorize(AccessRole.OOS_EVALUATOR, Partition.OOS)
    with pytest.raises(PermissionError):
        lifecycle.authorize(AccessRole.FINAL_AUDITOR, Partition.FINAL_HOLDOUT)

    lifecycle.freeze_candidate("a" * 64)
    with pytest.raises(PermissionError):
        lifecycle.authorize(AccessRole.OPTIMIZER, Partition.TRAIN)
    lifecycle.authorize(AccessRole.OOS_EVALUATOR, Partition.OOS)
    with pytest.raises(PermissionError):
        lifecycle.authorize(AccessRole.OOS_EVALUATOR, Partition.OOS)
    lifecycle.record_oos("oos-run-001", passed=True)
    lifecycle.open_final_holdout("approved-audit-001")
    lifecycle.authorize(AccessRole.FINAL_AUDITOR, Partition.FINAL_HOLDOUT)
    with pytest.raises(PermissionError):
        lifecycle.authorize(AccessRole.FINAL_AUDITOR, Partition.FINAL_HOLDOUT)
    lifecycle.complete(passed=False)
    assert lifecycle.state is EvaluationState.COMPLETED
    assert lifecycle.holdout_access_count == 1


def test_failed_oos_cannot_unlock_final_holdout() -> None:
    """A failed OOS result cannot be rescued by inspecting the final holdout."""
    lifecycle = ValidationLifecycle()
    lifecycle.freeze_candidate("b" * 64)
    lifecycle.authorize(AccessRole.OOS_EVALUATOR, Partition.OOS)
    lifecycle.record_oos("oos-run-failed", passed=False)
    with pytest.raises(PermissionError, match="passing"):
        lifecycle.open_final_holdout("not-allowed")


def test_experiment_store_is_append_only_and_persists_lineage(tmp_path) -> None:
    """Experiment definitions, events and candidates persist with immutable history."""
    # Use a disposable test database, separate from all existing runtime/account stores.
    store = ExperimentStore(tmp_path / "experiments.sqlite3")
    spec = make_experiment()
    store.create_experiment(spec)
    assert store.get_experiment(spec.experiment_id)["fingerprint"] == spec.fingerprint

    event_id = store.append_event(spec.experiment_id, "generation_completed", {"generation": 1})
    assert event_id > 0
    store.append_candidate(
        candidate_id="candidate-0001",
        experiment_id=spec.experiment_id,
        candidate_digest="c" * 64,
        family="genetic_programming",
        generation=1,
        parameters={"tree_depth": 3},
        metrics={"train_sharpe": 0.4},
        lineage={"parents": ["candidate-0000"], "mutation": "subtree"},
    )
    assert store.events(spec.experiment_id)[0]["payload"] == {"generation": 1}
    assert store.candidates(spec.experiment_id)[0]["lineage"]["mutation"] == "subtree"

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        with store._connection() as connection:
            connection.execute("UPDATE experiment_events SET event_type='changed' WHERE event_id=?", (event_id,))
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        with store._connection() as connection:
            connection.execute("DELETE FROM candidates WHERE candidate_id='candidate-0001'")
    with pytest.raises(sqlite3.IntegrityError):
        store.create_experiment(spec)
    with pytest.raises(sqlite3.IntegrityError, match="definitions are immutable"):
        with store._connection() as connection:
            connection.execute("UPDATE experiments SET track='crypto_portfolio' WHERE experiment_id=?",
                               (spec.experiment_id,))


def test_compute_engine_cpu_batch_matches_reference() -> None:
    """CPU population scores match a direct matrix multiplication reference."""
    # Small deterministic arrays pin shape and orientation semantics.
    features = np.arange(30, dtype=np.float64).reshape(10, 3)
    weights = np.asarray([[1.0, 0.0, -1.0], [0.5, 2.0, 0.0]], dtype=np.float64)
    engine = ComputeEngine(backend="cpu")
    actual = engine.batch_linear_scores(features, weights)
    expected = weights @ features.T
    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=1e-12)
    assert engine.info().backend == "numpy"

    with pytest.raises(ValueError, match="dimensions"):
        engine.batch_linear_scores(features, np.ones((2, 4)))
    with pytest.raises(ValueError, match="non-finite"):
        engine.batch_linear_scores(np.asarray([[np.nan]]), np.asarray([[1.0]]))


def test_compute_engine_auto_backend_is_consistent() -> None:
    """Auto mode returns correct data whether CuPy is installed or not."""
    # This test does not assert that a GPU exists on the current test runner.
    features = np.asarray([[1.0, 2.0], [3.0, 4.0]], dtype=np.float64)
    weights = np.asarray([[2.0, -1.0]], dtype=np.float64)
    engine = ComputeEngine(backend="auto")
    result = engine.batch_linear_scores(features, weights)
    np.testing.assert_allclose(result, weights @ features.T, rtol=1e-10, atol=1e-10)
    assert engine.info().backend in {"numpy", "cupy"}



def test_nse_exposed_test_period_cannot_be_declared_final_holdout() -> None:
    # The old 2024-2026 test set has already been inspected and cannot be called pristine.
    with pytest.raises(ValueError, match="historical test window is exposed"):
        make_experiment(
            final_holdout_start=datetime(2024, 1, 1, tzinfo=UTC),
            final_holdout_end=datetime(2025, 1, 1, tzinfo=UTC),
        )
