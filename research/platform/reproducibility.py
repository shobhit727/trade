"""Full reproducibility metadata for research experiments (audit F-023 / 7.21).

A Git commit alone does not reproduce a run. ``capture_environment_record``
snapshots the complete machine/software environment alongside every experiment,
and ``reproduce_check`` re-derives the record and fails loudly, listing every
field that differs, before any result is trusted as a reproduction.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import metadata as importlib_metadata
from typing import Any, Mapping

import numpy as np
import pandas as pd

from .compute import ComputeEngine

#: Python packages whose exact versions bind a run's numerical behaviour.
TRACKED_PACKAGES: tuple[str, ...] = (
    "numpy",
    "pandas",
    "optuna",
    "scipy",
    "scikit-learn",
)


def _package_version(distribution: str) -> str | None:
    """Return the installed distribution version, or None when not installed."""
    try:
        return importlib_metadata.version(distribution)
    except importlib_metadata.PackageNotFoundError:
        # An absent optional dependency is environment provenance, not an error.
        return None


def _git_working_tree_state(repo_root: str | None = None) -> dict[str, Any]:
    """Record clean/dirty working-tree state and the exact uncommitted diff, if any."""
    root = repo_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        diff = subprocess.run(
            ["git", "diff", "--no-color", "--no-ext-diff"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        # Git metadata is provenance; an unavailable git binary is recorded, not fatal.
        return {"clean": None, "uncommitted_diff": None, "error": f"{type(exc).__name__}: {exc}"}
    if status.returncode != 0:
        return {"clean": None, "uncommitted_diff": None, "error": status.stderr.strip()}
    dirty_lines = [line for line in status.stdout.splitlines() if line.strip()]
    return {
        "clean": not dirty_lines,
        # The diff captures tracked modifications; untracked files appear in status.
        "uncommitted_diff": diff.stdout if diff.returncode == 0 else None,
        "dirty_paths": dirty_lines,
    }


def capture_environment_record(
    *,
    seed: int,
    compute_backend: str = "auto",
    captured_at: datetime | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Snapshot every environment dimension audit 7.21 requires.

    The record is JSON-safe: every value serialises without NaN/Infinity and can be
    persisted through ExperimentStore.append_event or embedded in a result payload.
    """
    captured = (captured_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    engine = ComputeEngine(compute_backend)
    info = engine.info()
    try:
        import resource  # POSIX only; absent on Windows.

        max_rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except (ImportError, AttributeError):  # pragma: no cover - non-POSIX platforms.
        max_rss_kb = None
    record: dict[str, Any] = {
        "record_version": "1",
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
        },
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "architecture": platform.machine(),
        },
        "cpu_model": _cpu_model(),
        "ram_total_bytes": _total_ram_bytes(),
        "gpu": {
            "model": info.device_name,
            "driver_version": _nvidia_driver_version(),
            "cuda_version": _cuda_version(engine),
            "available": info.backend == "cupy",
        },
        "compute_backend": info.backend,
        "compute_fallback_reason": info.fallback_reason,
        "packages": {
            name: _package_version(name) for name in TRACKED_PACKAGES
        },
        "working_tree": _git_working_tree_state(repo_root),
        "random_seed": int(seed),
        # The NumPy bit-generator state is the full 624-word Mersenne Twister /
        # PCG64 state, not just the seed: restoring it resumes the exact stream.
        "numpy_random_state": _numpy_random_state(seed),
        "precision_mode": "float64",
        "thread_count": os.cpu_count(),
        "resource_use": {"max_rss_kb": max_rss_kb},
        "timezone": str(captured.astimezone().tzinfo),
        "timezone_rules": datetime.now().astimezone().tzname(),
        "captured_at": captured.isoformat(),
    }
    # Reject NaN/Infinity once here so every downstream JSON writer is safe.
    json.dumps(record, allow_nan=False)
    return record


def _cpu_model() -> str | None:
    try:
        if platform.system() == "Linux":
            with open("/proc/cpuinfo", encoding="utf-8") as handle:
                for line in handle:
                    if line.lower().startswith("model name") and ":" in line:
                        return line.split(":", 1)[1].strip()
        return platform.processor() or None
    except OSError:
        return None


def _total_ram_bytes() -> int | None:
    try:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemTotal") and ":" in line:
                    value, unit = line.split(":", 1)[1].split()
                    if unit.lower() == "kb":
                        return int(value) * 1024
        return None
    except (OSError, ValueError):
        return None


def _nvidia_driver_version() -> str | None:
    """Read the host driver version from the NVIDIA kernel module when present."""
    try:
        with open("/proc/driver/nvidia/version", encoding="utf-8") as handle:
            first = handle.readline().split()
        # Line 1: "NVRM" version marker; the kernel-module version follows it.
        for token in first:
            if token and token[0].isdigit():
                return token
        return None
    except OSError:
        return None


def _cuda_version(engine: ComputeEngine) -> str | None:
    # A live CuPy runtime can report its CUDA toolkit version truthfully.
    if engine.backend != "cupy":  # pragma: no cover - GPU hosts only.
        return None
    import cupy as cp  # noqa: PLC0415 - only imported when CUDA is live.

    return str(cp.cuda.runtime.runtimeGetVersion())


def _numpy_random_state(seed: int) -> dict[str, Any]:
    """Serialise the full NumPy bit-generator state for exact stream resumption."""
    generator = np.random.default_rng(seed)
    state = generator.bit_generator.state
    serialised: dict[str, Any] = {"bit_generator": state["bit_generator"]}
    for key, value in state.items():
        if isinstance(value, Mapping):
            # Nested bit-generator state words (PCG64 stores state/inc as ints).
            serialised[key] = {str(name): int(word) for name, word in value.items()}
        elif isinstance(value, int):
            serialised[key] = value
        else:
            serialised[key] = str(value)
    return serialised


class ReproducibilityMismatch(RuntimeError):
    """Raised when a re-derived environment record differs from the stored one."""

    def __init__(self, differing_fields: dict[str, tuple[Any, Any]]) -> None:
        self.differing_fields = differing_fields
        details = ", ".join(
            f"{path}: recorded={recorded!r} re-derived={rederived!r}"
            for path, (recorded, rederived) in sorted(differing_fields.items())
        )
        super().__init__(
            "environment record does not match the re-derived environment; "
            f"{len(differing_fields)} field(s) differ: {details}"
        )


#: Fields that legitimately vary between two captures on the same machine and
#: therefore never constitute a reproduction mismatch (capture timestamp, live
#: resource gauges, the compacted status listing).
_NON_COMPARING_FIELDS = frozenset({"captured_at", "resource_use", "timezone_rules"})


def _flatten(record: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, value in record.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, Mapping):
            flattened.update(_flatten(value, path))
        else:
            flattened[path] = value
    return flattened


def reproduce_check(
    recorded: Mapping[str, Any],
    *,
    seed: int,
    compute_backend: str = "auto",
    captured_at: datetime | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Re-derive the environment record and compare it against the stored one.

    Returns the re-derived record when the environments match. Raises
    ``ReproducibilityMismatch`` listing every differing field otherwise.
    """
    rederived = capture_environment_record(
        seed=seed,
        compute_backend=compute_backend,
        captured_at=captured_at,
        repo_root=repo_root,
    )
    recorded_flat = _flatten(dict(recorded))
    rederived_flat = _flatten(rederived)
    differing: dict[str, tuple[Any, Any]] = {}
    for path in sorted(set(recorded_flat) | set(rederived_flat)):
        top_level = path.split(".", 1)[0]
        if top_level in _NON_COMPARING_FIELDS:
            continue
        if path == "working_tree.uncommitted_diff":
            # A changed diff implies changed dirty paths; compare the boolean only.
            recorded_clean = recorded_flat.get("working_tree.clean")
            rederived_clean = rederived_flat.get("working_tree.clean")
            if recorded_clean != rederived_clean and recorded_clean is not None:
                differing[path] = (recorded_clean, rederived_clean)
            continue
        if recorded_flat.get(path) != rederived_flat.get(path):
            differing[path] = (recorded_flat.get(path), rederived_flat.get(path))
    if differing:
        raise ReproducibilityMismatch(differing)
    return rederived


@dataclass(frozen=True, slots=True)
class ReproducibilityBundle:
    """Complete run-scoped provenance persisted beside every experiment."""

    spec_fingerprint: str
    environment: dict[str, Any]
    started_at: datetime
    completed_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-safe experiment start/end and environment bundle."""
        return {
            "spec_fingerprint": self.spec_fingerprint,
            "environment": self.environment,
            "started_at": self.started_at.astimezone(timezone.utc).isoformat(),
            "completed_at": self.completed_at.astimezone(timezone.utc).isoformat(),
        }
