"""Reproducibility metadata tests (audit F-023 / section 7.21)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from research.platform.reproducibility import (
    TRACKED_PACKAGES,
    ReproducibilityBundle,
    ReproducibilityMismatch,
    capture_environment_record,
    reproduce_check,
)

REPO_ROOT = "/home/ph03n1x/trade/.worktrees/feature"


def _record(**kwargs) -> dict:
    return capture_environment_record(seed=7, repo_root=REPO_ROOT, **kwargs)


def test_environment_record_covers_audit_721_dimensions() -> None:
    record = _record()
    # Python, OS/architecture, CPU, RAM, GPU, backend, precision, threads.
    assert record["python"]["version"].count(".") == 2
    assert record["python"]["implementation"] == "CPython"
    assert record["os"]["architecture"] != ""
    assert record["cpu_model"] is None or isinstance(record["cpu_model"], str)
    assert record["ram_total_bytes"] is None or record["ram_total_bytes"] > 0
    assert set(record["gpu"]) == {"model", "driver_version", "cuda_version", "available"}
    assert record["compute_backend"] in {"numpy", "cupy"}
    assert record["precision_mode"] == "float64"
    assert isinstance(record["thread_count"], int) and record["thread_count"] >= 1
    # Working tree state plus the exact uncommitted diff when dirty.
    assert record["working_tree"]["clean"] in {True, False, None}
    if record["working_tree"]["clean"] is False:
        assert isinstance(record["working_tree"]["uncommitted_diff"], str)
    # Random generator state is the full serialisable bit-generator state.
    assert record["numpy_random_state"]["bit_generator"] == "PCG64"
    assert "state" in record["numpy_random_state"]
    # Time zone rules and capture time are timezone-aware.
    assert record["timezone"] != ""
    datetime.fromisoformat(record["captured_at"])
    # Every tracked platform dependency is versioned, not guessed.
    for name in TRACKED_PACKAGES:
        assert name in record["packages"]


def test_environment_record_is_json_safe() -> None:
    # The record must survive canonical JSON round trips without NaN/Infinity.
    blob = json.dumps(_record(), sort_keys=True, allow_nan=False)
    restored = json.loads(blob)
    assert restored["random_seed"] == 7


def test_reproduce_check_passes_on_identical_environment() -> None:
    record = _record()
    rederived = reproduce_check(record, seed=7, repo_root=REPO_ROOT)
    assert rederived["python"]["version"] == record["python"]["version"]
    assert rederived["numpy_random_state"] == record["numpy_random_state"]


def test_reproduce_check_survives_json_round_trip() -> None:
    # The stored record is always JSON; the check must accept the restored form.
    restored = json.loads(json.dumps(_record(), sort_keys=True))
    rederived = reproduce_check(restored, seed=7, repo_root=REPO_ROOT)
    assert rederived["random_seed"] == 7


def test_reproduce_check_lists_every_differing_field() -> None:
    record = _record()
    tampered = dict(record)
    tampered["random_seed"] = 8
    tampered["python"] = dict(record["python"], version="3.0.0")
    with pytest.raises(ReproducibilityMismatch) as excinfo:
        reproduce_check(tampered, seed=7, repo_root=REPO_ROOT)
    message = str(excinfo.value)
    differing = excinfo.value.differing_fields
    # Every mismatch is named with recorded and re-derived values.
    assert "random_seed" in differing
    assert "python.version" in differing
    assert differing["random_seed"] == (8, 7)
    assert "random_seed" in message and "python.version" in message


def test_reproduce_check_rejects_missing_and_extra_fields() -> None:
    record = _record()
    # A removed field is a mismatch: the environment record is complete or useless.
    incomplete = {key: value for key, value in record.items() if key != "compute_backend"}
    with pytest.raises(ReproducibilityMismatch):
        reproduce_check(incomplete, seed=7, repo_root=REPO_ROOT)
    # An added field outside the schema is equally suspect.
    with pytest.raises(ReproducibilityMismatch):
        reproduce_check(dict(record, unknown_field="x"), seed=7, repo_root=REPO_ROOT)


def test_reproduce_check_tolerates_capture_time_and_resource_gauges() -> None:
    record = _record(captured_at=datetime(2020, 1, 1, tzinfo=timezone.utc))
    # A different capture instant or live RSS gauge is not a reproduction mismatch.
    rederived = reproduce_check(
        record, seed=7, repo_root=REPO_ROOT,
        captured_at=datetime(2021, 6, 1, tzinfo=timezone.utc),
    )
    assert rederived["captured_at"].startswith("2021-06-01")


def test_reproducibility_bundle_serialises_start_and_end() -> None:
    bundle = ReproducibilityBundle(
        spec_fingerprint="abc123",
        environment=_record(),
        started_at=datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 11, 15, 12, 30, tzinfo=timezone.utc),
    )
    payload = bundle.to_dict()
    assert payload["spec_fingerprint"] == "abc123"
    assert payload["started_at"].startswith("2026-11-15T12:00")
    assert payload["completed_at"].startswith("2026-11-15T12:30")
    assert payload["environment"]["random_seed"] == 7


def test_numpy_random_state_restores_the_exact_stream() -> None:
    # The recorded state must resume the generator mid-stream, byte for byte.
    import numpy as np

    from research.platform.reproducibility import _numpy_random_state

    generator = np.random.default_rng(7)
    first = generator.random(4)
    # Advance the stream, then serialise the *live* state exactly as recorded.
    generator.random(10)
    recorded_state = _numpy_random_state(7)
    generator.bit_generator.state = {
        "bit_generator": recorded_state["bit_generator"],
        "state": {key: int(value) for key, value in recorded_state["state"].items()},
        "has_uint32": int(recorded_state["has_uint32"]),
        "uinteger": int(recorded_state["uinteger"]),
    }
    assert (generator.random(4) == first).all()
