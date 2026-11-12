"""Licence-approval gate and local-only API guard tests (audit F-004/F-008)."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from research.platform.adapters import materialize_non_holdout_partition
from research.platform.api import ensure_local_only_bind
from research.platform.data_catalog import DatasetManifest, LicenseStatus, ValueOrigin
from research.platform.domain import AlgorithmFamily, DataResolution, Market, ResearchTrack
from research.platform.experiments import ExperimentSpec
from research.platform.licensing import approve_dataset
from research.platform.runners import load_registered_bars
from research.platform.storage import ExperimentStore

UTC = timezone.utc


def _manifest(**updates: object) -> DatasetManifest:
    """Synthetic NSE manifest registered in REVIEW_REQUIRED state by default."""
    values: dict[str, object] = {
        "dataset_id": "nse-eod-v1",
        "market": Market.NSE,
        "provider": "unit-test",
        "source": "synthetic-bars-not-market-data",
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
        "license_status": LicenseStatus.REVIEW_REQUIRED,
        "license_reference": "pending-review",
        "value_origin": ValueOrigin.OBSERVED,
    }
    values.update(updates)
    return DatasetManifest(**values)  # type: ignore[arg-type]


def _spec(dataset_id: str = "nse-eod-v1") -> ExperimentSpec:
    """One NSE experiment whose only dataset is the synthetic fixture."""
    return ExperimentSpec(
        experiment_id="licence-test-experiment",
        market=Market.NSE,
        track=ResearchTrack.NSE_INDIVIDUAL,
        algorithm_family=AlgorithmFamily.EXISTING_STRATEGY,
        resolution=DataResolution.ONE_DAY,
        dataset_ids=(dataset_id,),
        random_seed=7,
        git_commit="0123456789abcdef0123456789abcdef01234567",
        code_version="licence-test",
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


def test_approval_requires_reference_and_reviewer(tmp_path) -> None:
    """Missing licence_reference or reviewed_by is rejected with an explicit reason."""
    store = ExperimentStore(tmp_path / "gate.sqlite3")
    store.register_dataset(_manifest())

    with pytest.raises(ValueError, match="licence_reference"):
        approve_dataset(store, "nse-eod-v1", licence_reference="   ", reviewed_by="alice")
    with pytest.raises(ValueError, match="licence_reference"):
        approve_dataset(store, "nse-eod-v1", licence_reference="", reviewed_by="alice")
    with pytest.raises(ValueError, match="reviewed_by"):
        approve_dataset(
            store,
            "nse-eod-v1",
            licence_reference="NSE EOD terms v2",
            reviewed_by="",
        )
    with pytest.raises(ValueError, match="reviewed_by"):
        approve_dataset(
            store,
            "nse-eod-v1",
            licence_reference="NSE EOD terms v2",
            reviewed_by="   ",
        )

    # Rejected reviews write nothing to the append-only log.
    assert store.dataset_licence_events("nse-eod-v1") == ()
    assert store.get_dataset("nse-eod-v1")["manifest"]["license_status"] == "review_required"


def test_two_approvals_append_two_ordered_records(tmp_path) -> None:
    """Every executed decision appends one record; order is preserved and content stored."""
    store = ExperimentStore(tmp_path / "gate.sqlite3")
    store.register_dataset(_manifest())

    first = approve_dataset(
        store,
        "nse-eod-v1",
        licence_reference="NSE EOD licence v2, clause 3",
        reviewed_by="alice",
    )
    second = approve_dataset(
        store,
        "nse-eod-v1",
        licence_reference="NSE EOD licence v3 renewal",
        reviewed_by="bob",
    )

    events = store.dataset_licence_events("nse-eod-v1")
    assert len(events) == 2
    assert events[0]["event_id"] < events[1]["event_id"]
    assert events[0]["payload"]["licence_reference"] == "NSE EOD licence v2, clause 3"
    assert events[0]["payload"]["reviewed_by"] == "alice"
    assert events[0]["payload"]["previous_status"] == "review_required"
    assert events[0]["payload"]["decision"] == "approve"
    assert events[1]["payload"]["licence_reference"] == "NSE EOD licence v3 renewal"
    assert events[1]["payload"]["reviewed_by"] == "bob"
    assert events[1]["payload"]["previous_status"] == "approved"
    assert first["event_id"] == events[0]["event_id"]
    assert second["event_id"] == events[1]["event_id"]

    # The event stream is append-only at the database level.
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        with store._connection() as connection:
            connection.execute(
                "UPDATE dataset_licence_events SET payload_json='{}' WHERE event_id=?",
                (events[0]["event_id"],),
            )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        with store._connection() as connection:
            connection.execute("DELETE FROM dataset_licence_events")


def test_unapproved_dataset_is_blocked_at_load(tmp_path) -> None:
    """load_registered_bars refuses a dataset before any licence event approves it."""
    frame = pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.5, 101.5],
            "volume": [1000.0, 1100.0],
        },
        index=pd.date_range("2016-01-04", periods=2, freq="D", tz="Asia/Kolkata"),
    )
    spec = _spec()
    safe_manifest = materialize_non_holdout_partition(
        _manifest(),
        frame,
        root=tmp_path / "partitions",
        final_holdout_start=spec.final_holdout_start,
    )
    store = ExperimentStore(tmp_path / "gate.sqlite3")
    store.create_experiment(spec)
    store.register_dataset(safe_manifest)

    # REVIEW_REQUIRED data is refused before any bar is read.
    with np.testing.assert_raises_regex(
        ValueError, "licence is not approved"
    ):
        load_registered_bars(
            store, spec, partition_data_root=tmp_path / "partitions", require_partitioned=True
        )

    # After an explicit licence review the same experiment loads.
    approve_dataset(
        store,
        spec.dataset_ids[0],
        licence_reference="synthetic-test-licence-approval",
        reviewed_by="licence-reviewer",
    )
    bars = load_registered_bars(
        store, spec, partition_data_root=tmp_path / "partitions", require_partitioned=True
    )
    assert list(bars) == ["TEST"]
    assert bars["TEST"].attrs["final_holdout_accessed"] is False


def test_api_refuses_non_loopback_bind_without_override(monkeypatch) -> None:
    """Non-loopback bind raises without RESEARCH_ALLOW_REMOTE_API=1."""
    monkeypatch.delenv("RESEARCH_ALLOW_REMOTE_API", raising=False)
    assert ensure_local_only_bind("127.0.0.1") is False
    assert ensure_local_only_bind("localhost") is False
    with pytest.raises(RuntimeError, match="RESEARCH_ALLOW_REMOTE_API"):
        ensure_local_only_bind("0.0.0.0")
    with pytest.raises(RuntimeError, match="non-loopback"):
        ensure_local_only_bind("192.168.1.10")
    # Any other value than exactly "1" does not unlock remote exposure.
    monkeypatch.setenv("RESEARCH_ALLOW_REMOTE_API", "true")
    with pytest.raises(RuntimeError, match="RESEARCH_ALLOW_REMOTE_API"):
        ensure_local_only_bind("0.0.0.0")


def test_api_remote_bind_override_warns(caplog, monkeypatch) -> None:
    """RESEARCH_ALLOW_REMOTE_API=1 permits a remote bind and logs a warning."""
    monkeypatch.setenv("RESEARCH_ALLOW_REMOTE_API", "1")
    with caplog.at_level(logging.WARNING, logger="research.platform.api"):
        assert ensure_local_only_bind("0.0.0.0") is True
    assert any(
        "remote exposure" in record.message and "RESEARCH_ALLOW_REMOTE_API=1" in record.message
        for record in caplog.records
    )
