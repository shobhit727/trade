"""Tests for transparent reuse of existing strategy registrations."""


import pytest

from research.platform.strategy_catalog import ExistingStrategyRegistry


def test_existing_strategy_registry_discovers_real_catalogue_entries() -> None:
    # The adapter must preserve existing registrations instead of creating duplicate classes.
    registry = ExistingStrategyRegistry()
    names = registry.names()
    assert len(names) >= 1
    assert "absolute_momentum" in names
    descriptor = registry.describe("absolute_momentum")
    assert descriptor.name == "absolute_momentum"
    assert descriptor.strategy_class
    assert descriptor.config_class
    assert isinstance(descriptor.defaults, dict)
    assert isinstance(descriptor.parameters, tuple)


def test_existing_strategy_registry_builds_shipped_default() -> None:
    # Baseline strategy construction uses the repository's original Config and class.
    registry = ExistingStrategyRegistry()
    strategy = registry.instantiate_default("absolute_momentum")
    assert strategy is not None
    assert strategy.__class__.__name__ == registry.describe("absolute_momentum").strategy_class


def test_existing_strategy_registry_rejects_unknown_parameter_fields() -> None:
    # Unknown config fields must fail rather than being silently ignored by the adapter.
    registry = ExistingStrategyRegistry()
    with pytest.raises(ValueError, match="unknown config fields"):
        registry.instantiate("absolute_momentum", {"not_a_real_parameter": 123})


# --- F-010: manifest gap audits (research/platform/data_catalog.py) --------

import json
from datetime import UTC, datetime, timedelta

import pandas as pd

from research.platform.data_catalog import (
    DatasetManifest,
    LicenseStatus,
    gap_audit,
    manifest_with_gap_audit,
)
from research.platform.domain import DataResolution, Market


def make_gap_manifest(**overrides: object) -> DatasetManifest:
    """Build a one-day-resolution manifest for gap-audit test cases."""
    values: dict[str, object] = {
        "dataset_id": "gap-audit-daily",
        "market": Market.NSE,
        "provider": "test-provider",
        "source": "synthetic-test-fixture",
        "instrument": "TEST",
        "exchange": "NSE",
        "category": "ohlcv",
        "resolution": DataResolution.ONE_DAY,
        "coverage_start": datetime(2026, 1, 1, tzinfo=UTC),
        "coverage_end": datetime(2026, 1, 11, tzinfo=UTC),
        "timezone": "UTC",
        "timestamp_convention": "bar-open",
        "acquired_at": datetime(2026, 1, 12, tzinfo=UTC),
        "update_frequency": "daily",
        "license_status": LicenseStatus.APPROVED,
        "license_reference": "test-only-licence-reference",
    }
    values.update(overrides)
    return DatasetManifest(**values)  # type: ignore[arg-type]


def test_gap_audit_perfect_coverage_reports_no_gaps() -> None:
    """A frame matching the declared cadence yields expected == actual, no gaps."""
    manifest = make_gap_manifest()
    index = pd.date_range("2026-01-01", periods=10, freq="1D", tz="UTC")
    frame = pd.DataFrame({"close": [10.0] * len(index)}, index=index)
    record = gap_audit(manifest, frame)
    assert record["schema"] == "gap-audit-v1"
    assert record["resolution"] == "1d"
    assert record["period_seconds"] == 86400
    assert record["expected_bars"] == 10
    assert record["actual_bars"] == 10
    assert record["gaps"] == []
    assert record["gap_count"] == 0
    assert record["missing_bars_total"] == 0
    assert record["first_observation"] == "2026-01-01T00:00:00+00:00"
    assert record["last_observation"] == "2026-01-10T00:00:00+00:00"


def test_gap_audit_planted_interior_gap_exact_interval_and_counts() -> None:
    """A planted 3-slot hole is reported with exact boundaries and bar counts."""
    manifest = make_gap_manifest()
    index = pd.date_range("2026-01-01", periods=10, freq="1D", tz="UTC").delete([3, 4, 5])
    frame = pd.DataFrame({"close": [10.0] * len(index)}, index=index)
    record = gap_audit(manifest, frame)
    assert record["expected_bars"] == 10
    assert record["actual_bars"] == 7
    assert record["gaps"] == [
        {
            "start": "2026-01-03T00:00:00+00:00",
            "end": "2026-01-07T00:00:00+00:00",
            "length_seconds": 345600.0,
            "missing_bars": 3,
        }
    ]
    assert record["missing_bars_total"] == 3
    # Measured accounting identity: observed + absent == declared expectation.
    assert record["actual_bars"] + record["missing_bars_total"] == record["expected_bars"]


def test_gap_audit_reports_leading_and_trailing_holes() -> None:
    """Holes before the first and after the last observation count against coverage."""
    manifest = make_gap_manifest()
    index = pd.DatetimeIndex(
        [datetime(2026, 1, 3, tzinfo=UTC), datetime(2026, 1, 4, tzinfo=UTC),
         datetime(2026, 1, 5, tzinfo=UTC), datetime(2026, 1, 8, tzinfo=UTC)]
    )
    frame = pd.DataFrame({"close": [10.0] * len(index)}, index=index)
    record = gap_audit(manifest, frame)
    assert record["actual_bars"] == 4
    assert record["missing_bars_total"] == 6
    assert record["actual_bars"] + record["missing_bars_total"] == record["expected_bars"]
    leading, interior, trailing = record["gaps"]
    assert leading["start"] == "2026-01-01T00:00:00+00:00"
    assert leading["end"] == "2026-01-03T00:00:00+00:00"
    assert leading["missing_bars"] == 2
    assert interior["start"] == "2026-01-05T00:00:00+00:00"
    assert interior["end"] == "2026-01-08T00:00:00+00:00"
    assert interior["missing_bars"] == 2
    assert trailing["start"] == "2026-01-08T00:00:00+00:00"
    assert trailing["end"] == "2026-01-11T00:00:00+00:00"
    assert trailing["missing_bars"] == 2


def test_gap_audit_single_slot_hole_at_hourly_resolution() -> None:
    """One skipped hourly bar is one gap of exactly one missing bar."""
    manifest = make_gap_manifest(
        dataset_id="gap-audit-hourly",
        resolution=DataResolution.ONE_HOUR,
        coverage_start=datetime(2026, 1, 1, tzinfo=UTC),
        coverage_end=datetime(2026, 1, 1, 6, tzinfo=UTC),
    )
    index = pd.date_range("2026-01-01", periods=6, freq="1h", tz="UTC").delete(3)
    frame = pd.DataFrame({"close": [1.0] * len(index)}, index=index)
    record = gap_audit(manifest, frame)
    assert record["expected_bars"] == 6
    assert record["actual_bars"] == 5
    assert record["gaps"] == [
        {
            "start": "2026-01-01T02:00:00+00:00",
            "end": "2026-01-01T04:00:00+00:00",
            "length_seconds": 7200.0,
            "missing_bars": 1,
        }
    ]


def test_gap_audit_weekly_resolution_is_fixed_length() -> None:
    """Weekly bars are exactly 7 days apart in UTC, so they audit normally."""
    manifest = make_gap_manifest(
        dataset_id="gap-audit-weekly",
        resolution=DataResolution.ONE_WEEK,
        coverage_start=datetime(2026, 1, 5, tzinfo=UTC),
        coverage_end=datetime(2026, 2, 2, tzinfo=UTC),
    )
    index = pd.DatetimeIndex(
        [datetime(2026, 1, d, tzinfo=UTC) for d in (5, 12, 26)]
    )
    frame = pd.DataFrame({"close": [1.0] * len(index)}, index=index)
    record = gap_audit(manifest, frame)
    assert record["period_seconds"] == 604800
    assert record["expected_bars"] == 4
    assert record["actual_bars"] == 3
    assert record["gaps"] == [{
        "start": "2026-01-12T00:00:00+00:00",
        "end": "2026-01-26T00:00:00+00:00",
        "length_seconds": 1209600.0,
        "missing_bars": 1,
    }]
    assert record["actual_bars"] + record["missing_bars_total"] == record["expected_bars"]


def test_gap_audit_spacing_equal_to_period_is_not_a_gap() -> None:
    """Adjacent observations one declared period apart are the cadence itself."""
    manifest = make_gap_manifest()
    index = pd.date_range("2026-01-01", periods=10, freq="1D", tz="UTC")
    frame = pd.DataFrame({"close": [1.0] * 10}, index=index)
    record = gap_audit(manifest, frame)
    assert record["gaps"] == []


def test_gap_audit_no_quality_grade_is_inferred() -> None:
    """The audit reports measured facts only; no score or grade is added."""
    manifest = make_gap_manifest()
    index = pd.date_range("2026-01-01", periods=10, freq="1D", tz="UTC").delete([3, 4, 5])
    frame = pd.DataFrame({"close": [10.0] * len(index)}, index=index)
    record = gap_audit(manifest, frame)
    assert not ({"quality_score", "grade", "complete", "completeness"} & record.keys())


def test_gap_audit_rejects_broken_frames_and_undated_resolutions() -> None:
    """Duplicate, non-chronological, naive or out-of-coverage data is refused."""
    manifest = make_gap_manifest()
    good = pd.date_range("2026-01-01", periods=3, freq="1D", tz="UTC")
    cases = [
        (
            pd.DataFrame({"close": [1.0, 1.0]}, index=pd.DatetimeIndex(
                [datetime(2026, 1, 2, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC)])),
            "chronologically ordered",
        ),
        (
            pd.DataFrame({"close": [1.0, 1.0]}, index=pd.DatetimeIndex(
                [datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC)])),
            "unique timestamps",
        ),
        (
            pd.DataFrame({"close": [1.0]}, index=pd.DatetimeIndex([datetime(2026, 1, 1)])),
            "timezone-aware",
        ),
        (
            pd.DataFrame({"close": [1.0]}, index=pd.DatetimeIndex([datetime(2025, 12, 31, tzinfo=UTC)])),
            "beyond the manifest",
        ),
        (
            pd.DataFrame({"close": [1.0]}, index=pd.DatetimeIndex([datetime(2026, 1, 12, tzinfo=UTC)])),
            "beyond the manifest",
        ),
        (pd.DataFrame({"close": []}, index=pd.DatetimeIndex([], tz="UTC")), "at least one observation"),
    ]
    for frame, message in cases:
        with pytest.raises(ValueError, match=message):
            gap_audit(manifest, frame)

    # Monthly is calendar-anchored (no honest constant-period expectation).
    with pytest.raises(ValueError, match="calendar-anchored"):
        gap_audit(
            make_gap_manifest(resolution=DataResolution.ONE_MONTH, dataset_id="gap-monthly"),
            pd.DataFrame({"close": [1.0, 1.0]}, index=pd.DatetimeIndex(
                [datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 2, 1, tzinfo=UTC)])),
        )
    # Tick and order-book resolutions have no uniform bar period.
    with pytest.raises(ValueError, match="no uniform bar period"):
        gap_audit(
            make_gap_manifest(resolution=DataResolution.TICK, dataset_id="gap-tick"),
            pd.DataFrame({"close": [1.0, 1.0]}, index=pd.DatetimeIndex(
                [datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)])),
        )


def test_manifest_with_gap_audit_follows_quality_report_canonical_idiom() -> None:
    """The audit is stored as canonical JSON in extra_metadata on a new copy."""
    manifest = make_gap_manifest()
    index = pd.date_range("2026-01-01", periods=10, freq="1D", tz="UTC").delete([3, 4, 5])
    frame = pd.DataFrame({"close": [10.0] * len(index)}, index=index)
    record = gap_audit(manifest, frame)
    audited = manifest_with_gap_audit(manifest, frame)
    payload = audited.extra_metadata["gap_audit_json"]
    assert json.loads(payload) == record
    assert payload == json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False)
    # The source manifest is immutable; the audited copy carries the record.
    assert "gap_audit_json" not in manifest.extra_metadata
    assert audited.fingerprint != manifest.fingerprint
    # Round trip through the manifest's JSON-safe dict serialisation.
    assert json.loads(json.dumps(audited.to_dict()["extra_metadata"]))["gap_audit_json"] == payload
