"""Out-of-sample boundary independence verification (audit F-005).

Five proof obligations for the independent OOS boundary:

(a) Selection invariance: model selection must be identical when OOS rows are
    replaced with a different price path, proving selection never reads OOS.
    Candidate/digest equality is deliberately NOT asserted: digests embed
    ``bars_sha256`` over the whole panel including OOS rows, so digests differ
    by construction even with zero leakage. Selection outputs (parameters and
    TRAIN/VALIDATION scores) must be invariant instead.
(b) Partition isolation: the pre-materialised non-holdout copy is cut at the
    final-holdout boundary (it includes the OOS window, which IS evaluated),
    the worker-facing load is clipped at ``oos_end``, and the copy is the only
    consulted artifact: destroying the original source still loads, corrupting
    the copy fails the checksum.
(c) One-time holdout access: a repeated final-holdout access is refused and the
    refusal itself is durably recorded as a lifecycle event without state change.
(d) Purge/embargo at the validation/OOS seam: label overlap across the seam is
    purged, no training index falls within the embargo of the OOS start, and
    the partition plan cannot place OOS inside the validation embargo.
(e) Strict default: with ``RESEARCH_REQUIRE_PARTITIONED_DATA`` unset the strict
    partition policy engages for crypto loads even when a checksum-valid legacy
    combined source exists.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research.platform.adapters import materialize_non_holdout_partition
from research.platform.data_catalog import DatasetManifest, LicenseStatus, ValueOrigin
from research.platform.domain import AlgorithmFamily, DataResolution, Market, ResearchTrack
from research.platform.experiments import ExperimentSpec
from research.platform.jobs import ResearchJobManager
from research.platform.runners import (
    ExistingStrategyOptimizerJobRunner,
    load_registered_bars,
)
from research.platform.storage import ExperimentStore
from research.platform.validation import (
    AccessRole,
    Partition,
    SplitPlan,
    TimeWindow,
    ValidationLifecycle,
    purged_walk_forward_split,
)


UTC = timezone.utc
JAN = datetime(2026, 1, 1, tzinfo=UTC)


def _boundary_spec(experiment_id: str, **overrides: object) -> ExperimentSpec:
    """NSE experiment with the platform's post-2026-10 exposed-test guard windows."""
    values: dict[str, object] = {
        "experiment_id": experiment_id,
        "market": Market.NSE,
        "track": ResearchTrack.NSE_INDIVIDUAL,
        "algorithm_family": AlgorithmFamily.RANDOM_SEARCH,
        "resolution": DataResolution.ONE_DAY,
        "dataset_ids": ("boundary-nse-data-v1",),
        "random_seed": 37,
        "git_commit": "0123456789abcdef0123456789abcdef01234567",
        "code_version": "boundary-test",
        "training_start": datetime(2016, 1, 1, tzinfo=UTC),
        "training_end": datetime(2018, 1, 1, tzinfo=UTC),
        "validation_start": datetime(2018, 1, 1, tzinfo=UTC),
        "validation_end": datetime(2020, 1, 1, tzinfo=UTC),
        "oos_start": datetime(2026, 10, 2, tzinfo=UTC),
        "oos_end": datetime(2026, 10, 16, tzinfo=UTC),
        "final_holdout_start": datetime(2026, 10, 16, tzinfo=UTC),
        "final_holdout_end": datetime(2026, 11, 8, tzinfo=UTC),
        "cost_model_id": "nse-delivery-cost-model",
        "execution_model_id": "next-open-participation-impact-v1",
        "objectives": ("net_return", "max_drawdown", "turnover"),
        "parameters": {
            "strategy_name": "absolute_momentum",
            "strategy_parameters": {"period": 10, "threshold": 0.0},
            "optimization": {
                "budget": 6,
                "validation_candidates": 2,
                "objective": "sharpe",
            },
            "execution_assumptions": {
                "slippage_bps": 5,
                "impact_coefficient_bps": 10,
                "max_participation": 0.05,
                "max_gross_exposure": 1.0,
                "periods_per_year": 252,
            },
        },
        "created_at": datetime(2026, 11, 8, tzinfo=UTC),
    }
    values.update(overrides)
    return ExperimentSpec(**values)  # type: ignore[arg-type]


def _register_nse_store(path: Path, spec: ExperimentSpec) -> ExperimentStore:
    """Store with one approved synthetic NSE OHLCV dataset registration."""
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
        processing_history=("generated inside unit test",),
    ))
    return store


def _selection_bars(oos_close: np.ndarray) -> dict[str, pd.DataFrame]:
    """Synthetic trending bars whose OOS window carries the caller's price path."""
    index = pd.date_range("2015-01-01", "2026-11-09", freq="D", tz="Asia/Kolkata")
    step = np.arange(len(index), dtype=np.float64)
    close = 100.0 + 0.015 * step + 3.0 * np.sin(step / 12.0)
    utc_index = index.tz_convert("UTC")
    oos_mask = (utc_index >= pd.Timestamp("2026-10-02", tz=UTC)) & (
        utc_index < pd.Timestamp("2026-10-16", tz=UTC)
    )
    assert int(oos_mask.sum()) == len(oos_close)
    close = close.copy()
    close[oos_mask] = oos_close
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


def _run_optimizer(spec: ExperimentSpec, bars: dict[str, pd.DataFrame], path: Path) -> dict:
    """Run the existing-strategy optimizer worker once on injected synthetic bars."""
    store = _register_nse_store(path, spec)
    manager = ResearchJobManager(store, max_workers=1, max_queued=1)
    runner = ExistingStrategyOptimizerJobRunner(
        bar_loader=lambda current_store, current_spec: bars
    )
    manager.register_runner("existing_strategy_optimization", runner)
    try:
        job_id = manager.submit(spec.experiment_id, "existing_strategy_optimization")
        job = manager.wait(job_id, timeout=180)
        assert job["status"] == "succeeded", job["error_message"]
        return job["result"]
    finally:
        manager.shutdown(wait=True, cancel_pending=True)


def test_selection_is_invariant_when_oos_rows_are_replaced_with_noise(tmp_path) -> None:
    """Case (a): selection outputs are identical under a fully different OOS path."""
    count = 14
    rising_oos = np.linspace(120.0, 220.0, count)  # strong rally in OOS
    falling_oos = np.linspace(220.0, 120.0, count)  # strong crash in OOS

    baseline_spec = _boundary_spec("boundary-selection-baseline")
    noised_spec = _boundary_spec("boundary-selection-noised-oos")
    assert baseline_spec.fingerprint != noised_spec.fingerprint

    baseline = _run_optimizer(
        baseline_spec,
        _selection_bars(rising_oos),
        tmp_path / "baseline.sqlite3",
    )
    noised = _run_optimizer(
        noised_spec,
        _selection_bars(falling_oos),
        tmp_path / "noised.sqlite3",
    )

    # Preconditions: the manipulation changed the OOS outcome, so the two runs
    # genuinely saw different OOS rows and both actually evaluated OOS.
    def _oos_net_return(result: dict) -> float:
        oos = next(
            item for item in result["final_evaluation"]["partitions"]
            if item["partition"] == "out_of_sample"
        )
        return float(oos["metrics"]["total_return"])

    baseline_oos = _oos_net_return(baseline)
    noised_oos = _oos_net_return(noised)
    assert baseline_oos != noised_oos
    assert baseline_oos > 0.0  # rally produced a positive OOS return
    assert noised_oos < baseline_oos  # crash path cannot beat it

    # The validation shortlist must have distinct scores in this fixture, so the
    # digest tie-break in max() can never engage: selection is score-determined.
    baseline_scores = [row["validation_score"] for row in baseline["validation_shortlist"]]
    noised_scores = [row["validation_score"] for row in noised["validation_shortlist"]]
    assert len(set(baseline_scores)) == len(baseline_scores)

    # Selection invariance: identical chosen parameters and identical TRAIN and
    # VALIDATION scores, even though every persisted digest differs (digests
    # embed bars_sha256 over the whole panel including OOS rows by design).
    assert baseline_scores == noised_scores
    selected_baseline = baseline["selected_candidate"]
    selected_noised = noised["selected_candidate"]
    assert selected_baseline["parameters"] == selected_noised["parameters"]
    assert selected_baseline["train_score"] == selected_noised["train_score"]
    assert selected_baseline["validation_score"] == selected_noised["validation_score"]
    assert (
        selected_baseline["candidate_digest"] != selected_noised["candidate_digest"]
    )  # digests are panel-bound, not selection-determining: see score assertions above

    # The selection decision event also carries only partition-safe fields.
    for store_path, spec in (
        (tmp_path / "baseline.sqlite3", baseline_spec),
        (tmp_path / "noised.sqlite3", noised_spec),
    ):
        store = ExperimentStore(store_path)
        selection_events = [
            event for event in store.events(spec.experiment_id)
            if event["event_type"] == "existing_strategy_optimization_selected"
        ]
        assert len(selection_events) == 1
        payload = selection_events[0]["payload"]
        assert payload["validation_score"] == selected_baseline["validation_score"]
        assert payload["final_holdout_accessed"] is False


def test_partition_copy_excludes_holdout_and_never_consults_source(tmp_path) -> None:
    """Case (b): the safe copy ends at the holdout boundary; the source is dead weight."""
    spec = _boundary_spec(
        "boundary-partition-copy",
        oos_end=datetime(2026, 10, 12, tzinfo=UTC),  # strictly before the holdout boundary
    )
    source_dir = tmp_path / "combined-source"
    source_dir.mkdir(parents=True)
    source_csv = source_dir / "TEST_1d.csv"

    # Build the registered combined source as a real file with recorded provenance.
    index = pd.date_range("2015-01-01", "2026-11-09", freq="D", tz="UTC")
    step = np.arange(len(index), dtype=np.float64)
    close = 100.0 + 0.015 * step + 3.0 * np.sin(step / 12.0)
    combined = pd.DataFrame(
        {
            "open": close - 0.05,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.full(len(index), 50000.0),
        },
        index=index,
    )
    combined.to_csv(source_csv, index=True, index_label="timestamp", date_format="%Y-%m-%dT%H:%M:%S%z")
    source_sha256 = hashlib.sha256(source_csv.read_bytes()).hexdigest()

    parsed = pd.read_csv(source_csv, index_col="timestamp")
    parsed.index = pd.DatetimeIndex(pd.to_datetime(parsed.index, utc=True))
    parsed.index.name = "timestamp"

    manifest = DatasetManifest(
        dataset_id=spec.dataset_ids[0],
        market=Market.NSE,
        provider="unit-test",
        source="combined-source/TEST_1d.csv",
        instrument="TEST",
        exchange="NSE",
        category="ohlcv",
        resolution=DataResolution.ONE_DAY,
        coverage_start=combined.index[0].to_pydatetime(),
        coverage_end=combined.index[-1].to_pydatetime(),
        timezone="UTC",
        timestamp_convention="synthetic-daily-bar-index",
        acquired_at=datetime(2026, 11, 8, tzinfo=UTC),
        update_frequency="daily",
        license_status=LicenseStatus.APPROVED,
        license_reference="synthetic-test-fixture-only",
        value_origin=ValueOrigin.OBSERVED,
        extra_metadata={"file_sha256": source_sha256},
    )
    root = tmp_path / "partition-store"
    safe_manifest = materialize_non_holdout_partition(
        manifest,
        parsed,
        root=root,
        final_holdout_start=spec.final_holdout_start,
        max_abs_close_return=0.20,
    )

    # The physical copy is cut at the FINAL-holdout boundary: OOS rows are part of
    # the evaluatable non-holdout record, only the locked holdout is excluded.
    copy_path = root / spec.dataset_ids[0] / "non_holdout.csv"
    assert copy_path.is_file()
    copy_frame = pd.read_csv(copy_path, index_col="timestamp")
    copy_index = pd.DatetimeIndex(pd.to_datetime(copy_frame.index, utc=True))
    expected_rows = parsed.index.tz_convert("UTC") < pd.Timestamp(spec.final_holdout_start)
    assert len(copy_frame) == int(expected_rows.sum())
    assert safe_manifest.extra_metadata["research_partition_bars"] == str(len(copy_frame))
    assert safe_manifest.extra_metadata["research_partition_before"] == "2026-10-16T00:00:00+00:00"
    assert hashlib.sha256(copy_path.read_bytes()).hexdigest() == (
        safe_manifest.extra_metadata["research_partition_sha256"]
    )
    assert copy_index.max() < pd.Timestamp(spec.final_holdout_start)
    # The copy includes the OOS window (which IS evaluated) but ends at the holdout.
    assert copy_index.max() >= pd.Timestamp(spec.oos_start)

    store = ExperimentStore(tmp_path / "partition-copy.sqlite3")
    store.create_experiment(spec)
    store.register_dataset(safe_manifest)

    def _loaded_frame() -> pd.DataFrame:
        bars = load_registered_bars(store, spec, partition_data_root=root)
        frame = bars["TEST"]
        assert frame.attrs["data_access_mode"] == "pre_materialised_non_holdout_partition"
        assert frame.attrs["final_holdout_accessed"] is False
        return frame

    loaded = _loaded_frame()
    loaded_index = loaded.index.tz_convert("UTC")
    # The worker-facing load is clipped at oos_end even though the copy holds more.
    assert loaded_index.max() < pd.Timestamp(spec.oos_end)
    assert len(loaded) < len(copy_frame)
    assert loaded_index.max() == copy_index[copy_index < pd.Timestamp(spec.oos_end)].max()

    # Independence proof: the ORIGINAL source is destroyed; the copy alone suffices.
    source_csv.unlink()
    assert not source_csv.exists()
    reloaded = _loaded_frame()
    assert len(reloaded) == len(loaded)
    assert reloaded.index.tz_convert("UTC").max() == loaded_index.max()
    assert float(reloaded["close"].iloc[-1]) == float(loaded["close"].iloc[-1])

    # Negative control: corrupting the COPY fails the checksum, proving the copy
    # (not the absent source) is the consulted artifact for integrity.
    copy_path.write_text(copy_path.read_text(encoding="utf-8") + "9999-01-01T00:00:00+00:00,1,1,1,1,1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum does not match"):
        load_registered_bars(store, spec, partition_data_root=root)


def test_repeated_holdout_access_is_refused_and_recorded(tmp_path) -> None:
    """Case (c): second holdout access raises and the refusal becomes a durable event."""
    spec = _boundary_spec("boundary-holdout-refusal")
    store = ExperimentStore(tmp_path / "holdout-refusal.sqlite3")
    store.create_experiment(spec)
    lifecycle_id = "holdout-once-001"
    lifecycle = ValidationLifecycle(
        store=store,
        experiment_id=spec.experiment_id,
        lifecycle_id=lifecycle_id,
    )
    lifecycle.freeze_candidate("c" * 64)
    lifecycle.authorize(AccessRole.OOS_EVALUATOR, Partition.OOS)
    lifecycle.record_oos("oos-evaluation-001", passed=True)
    lifecycle.open_final_holdout("audit-approval-001")

    # First audited access is granted exactly once.
    lifecycle.authorize(AccessRole.FINAL_AUDITOR, Partition.FINAL_HOLDOUT)
    assert lifecycle.holdout_access_count == 1

    # The second access attempt is refused ...
    with pytest.raises(PermissionError, match="only once"):
        lifecycle.authorize(AccessRole.FINAL_AUDITOR, Partition.FINAL_HOLDOUT)
    # ... and the refusal is recorded in the in-memory event trail.
    memory_refusals = [
        event for event in lifecycle.events if event["event"] == "holdout_access_refused"
    ]
    assert len(memory_refusals) == 1
    assert memory_refusals[0]["access_attempts"] == 1

    # The refusal is durable, correctly ordered, and did not mutate the state.
    persisted = store.get_validation_lifecycle(spec.experiment_id, lifecycle_id)
    names = [event["event"] for event in persisted["events"]]
    assert names == [
        "candidate_frozen",
        "oos_evaluation_started",
        "oos_recorded",
        "holdout_opened",
        "holdout_accessed",
        "holdout_access_refused",
    ]
    assert persisted["state"] == "holdout_opened"
    assert persisted["holdout_access_count"] == 1
    refusal = persisted["events"][-1]
    assert refusal["payload"]["lifecycle_id"] == lifecycle_id
    assert refusal["payload"]["access_attempts"] == 1

    # A further attempt is refused and recorded again; completion still works.
    with pytest.raises(PermissionError, match="only once"):
        lifecycle.authorize(AccessRole.FINAL_AUDITOR, Partition.FINAL_HOLDOUT)
    persisted_after = store.get_validation_lifecycle(spec.experiment_id, lifecycle_id)
    assert [event["event"] for event in persisted_after["events"]].count(
        "holdout_access_refused"
    ) == 2
    lifecycle.complete(passed=True)
    assert store.get_validation_lifecycle(spec.experiment_id, lifecycle_id)["state"] == "completed"

    # Negative controls: while the holdout is still sealed, access is refused
    # WITHOUT recording a refusal event (only an opened holdout can be re-accessed).
    sealed = ValidationLifecycle(
        store=store,
        experiment_id=spec.experiment_id,
        lifecycle_id="holdout-sealed-002",
    )
    with pytest.raises(PermissionError, match="sealed"):
        sealed.authorize(AccessRole.FINAL_AUDITOR, Partition.FINAL_HOLDOUT)
    sealed.freeze_candidate("d" * 64)
    sealed.authorize(AccessRole.OOS_EVALUATOR, Partition.OOS)
    sealed.record_oos("oos-evaluation-002", passed=True)
    with pytest.raises(PermissionError, match="sealed"):
        sealed.authorize(AccessRole.FINAL_AUDITOR, Partition.FINAL_HOLDOUT)
    sealed_events = store.get_validation_lifecycle(
        spec.experiment_id, "holdout-sealed-002"
    )["events"]
    assert not any(
        event["event"] == "holdout_access_refused" for event in sealed_events
    )


def test_purge_and_embargo_guard_the_validation_oos_seam() -> None:
    """Case (d): label overlap across the seam is purged; embargo edges are exact."""
    decisions = pd.date_range(JAN, periods=31, freq="D", tz="UTC").to_pydatetime()
    label_starts = list(decisions)
    label_span = timedelta(days=5)
    label_ends = [decision + label_span for decision in decisions]

    oos_start = datetime(2026, 1, 20, tzinfo=UTC)
    oos_end = datetime(2026, 1, 24, tzinfo=UTC)
    embargo = timedelta(days=3)

    # The same splitter guards the validation/OOS seam when pointed at the OOS window.
    seam = purged_walk_forward_split(
        decisions, label_starts, label_ends,
        TimeWindow(oos_start, oos_end),
        embargo=embargo,
    )
    # Decisions at or after oos_end are walk-forward excluded, never training data.
    assert seam.excluded_indices == tuple(range(23, 31))
    assert seam.validation_indices == tuple(range(19, 23))
    # Labels overlapping [oos_start - embargo, oos_end + embargo) are purged.
    assert seam.purged_indices == tuple(range(12, 19))
    assert seam.training_indices == tuple(range(0, 12))

    # No training decision falls within the embargo of oos_start: the last
    # training sample's label ends exactly at the embargo edge (half-open
    # semantics: a label ending AT oos_start - embargo does not overlap it).
    last = seam.training_indices[-1]
    assert decisions[last] == oos_start - embargo - label_span
    assert label_ends[last] == oos_start - embargo
    assert all(
        label_ends[i] <= oos_start - embargo for i in seam.training_indices
    )
    # Every decision inside the embargo of oos_start is purged, never trained.
    embargo_decisions = [
        index for index, decision in enumerate(decisions)
        if oos_start - embargo <= decision < oos_start
    ]
    assert embargo_decisions == [16, 17, 18]
    assert set(embargo_decisions).issubset(set(seam.purged_indices))

    # The chronological validation fold purges identically around validation_end,
    # and removing the embargo narrows the purge by exactly the embargo length.
    validation_start = datetime(2026, 1, 10, tzinfo=UTC)
    validation_end = datetime(2026, 1, 20, tzinfo=UTC)
    fold = purged_walk_forward_split(
        decisions, label_starts, label_ends,
        TimeWindow(validation_start, validation_end),
        embargo=embargo,
    )
    assert fold.training_indices == (0, 1)
    assert fold.purged_indices == tuple(range(2, 9))
    assert fold.validation_indices == tuple(range(9, 19))
    assert fold.excluded_indices == tuple(range(19, 31))
    for index in fold.training_indices:
        assert label_ends[index] <= validation_start - embargo

    unembargoed = purged_walk_forward_split(
        decisions, label_starts, label_ends,
        TimeWindow(validation_start, validation_end),
    )
    assert unembargoed.training_indices == tuple(range(0, 5))
    assert unembargoed.purged_indices == tuple(range(5, 9))

    # The partition plan cannot place OOS inside the validation embargo, but the
    # exact embargo edge is an allowed seam.
    plan_windows = dict(
        train=TimeWindow(datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 5, tzinfo=UTC)),
        validation=TimeWindow(validation_start, validation_end),
        final_holdout=TimeWindow(datetime(2026, 1, 30, tzinfo=UTC), datetime(2026, 2, 6, tzinfo=UTC)),
        embargo=embargo,
    )
    allowed = SplitPlan(oos=TimeWindow(datetime(2026, 1, 23, tzinfo=UTC), datetime(2026, 1, 27, tzinfo=UTC)), **plan_windows)
    assert allowed.protocol_id == "chronological-v1"
    with pytest.raises(ValueError, match="embargo"):
        SplitPlan(oos=TimeWindow(datetime(2026, 1, 22, tzinfo=UTC), datetime(2026, 1, 26, tzinfo=UTC)), **plan_windows)


def _crypto_spec(experiment_id: str, dataset_id: str) -> ExperimentSpec:
    """Crypto experiment whose loader path exercises the strict partition policy."""
    return ExperimentSpec(
        experiment_id=experiment_id,
        market=Market.CRYPTO,
        track=ResearchTrack.CRYPTO_INDIVIDUAL,
        algorithm_family=AlgorithmFamily.EXISTING_STRATEGY,
        resolution=DataResolution.ONE_HOUR,
        dataset_ids=(dataset_id,),
        random_seed=13,
        git_commit="0123456789abcdef0123456789abcdef01234567",
        code_version="boundary-crypto-test",
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


def _write_crypto_csv(path: Path, stamps: list[int], closes: list[float]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = ["timestamp,open,high,low,close,volume"]
    for stamp, price in zip(stamps, closes, strict=True):
        rows.append(f"{stamp},{price},{price * 1.01},{price * 0.99},{price},1000")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_strict_partition_policy_defaults_engage_for_crypto(tmp_path, monkeypatch) -> None:
    """Case (e): with the env unset, crypto loads fail closed on legacy combined data."""
    monkeypatch.delenv("RESEARCH_REQUIRE_PARTITIONED_DATA", raising=False)
    dataset_id = "boundary-crypto-btcinr-1h"
    spec = _crypto_spec("boundary-crypto-strict-default", dataset_id)
    source = tmp_path / "binance" / "BTCINR_1h.csv"
    stamps = [
        int(pd.Timestamp("2025-01-01T00:00:00Z").timestamp() * 1000),
        int(pd.Timestamp("2025-01-01T01:00:00Z").timestamp() * 1000),
        int(pd.Timestamp("2025-01-01T02:00:00Z").timestamp() * 1000),
        int(pd.Timestamp("2025-01-01T03:00:00Z").timestamp() * 1000),
    ]
    digest = _write_crypto_csv(source, stamps, [8000000.0, 8010000.0, 8020000.0, 8030000.0])

    store = ExperimentStore(tmp_path / "crypto-strict.sqlite3")
    store.create_experiment(spec)
    store.register_dataset(DatasetManifest(
        dataset_id=dataset_id,
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

    # Precondition: the legacy source is present AND checksum-valid, so the
    # refusal below is a policy decision, not missing or corrupted data.
    assert source.is_file()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest

    # Default strict policy (1) engages: no physical non-holdout partition exists.
    with pytest.raises(ValueError, match="no physical non-holdout partition"):
        load_registered_bars(
            store,
            spec,
            crypto_data_root=tmp_path,
            partition_data_root=tmp_path / "no-partitions",
        )

    # Control: the explicit opt-out loads the same valid source, clipped before
    # the OOS end boundary (the third hourly bar is the last visible row).
    bars = load_registered_bars(
        store,
        spec,
        crypto_data_root=tmp_path,
        partition_data_root=tmp_path / "no-partitions",
        require_partitioned=False,
    )
    frame = bars["BTCINR"]
    assert len(frame) == 3
    assert frame.index.tz_convert("UTC").max() < pd.Timestamp(spec.oos_end)
    assert float(frame["close"].iloc[-1]) == 8020000.0
    assert frame.attrs["data_access_mode"] == "legacy_combined_source_clipped_after_read"
