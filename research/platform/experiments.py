"""Experiment specifications and deterministic configuration fingerprints."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from .data_catalog import DataAvailabilityCatalog
from .domain import AlgorithmFamily, DataResolution, MARKET_SPECS, Market, ResearchTrack, TRACK_MARKET


@dataclass(frozen=True, slots=True)
class ExperimentSpec:
    """Immutable definition of one reproducible research run."""

    experiment_id: str
    market: Market
    track: ResearchTrack
    algorithm_family: AlgorithmFamily
    resolution: DataResolution
    dataset_ids: tuple[str, ...]
    random_seed: int
    git_commit: str
    code_version: str
    training_start: datetime
    training_end: datetime
    validation_start: datetime
    validation_end: datetime
    oos_start: datetime
    oos_end: datetime
    final_holdout_start: datetime
    final_holdout_end: datetime
    cost_model_id: str
    execution_model_id: str
    objectives: tuple[str, ...]
    compute_backend: str = "numpy"
    compute_device: str = "unknown"
    parameters: dict[str, Any] = field(default_factory=dict)
    embargo_seconds: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        # Ensure each track maps to exactly one financial environment.
        if TRACK_MARKET[self.track] is not self.market:
            raise ValueError("research track does not belong to the requested market")
        if not self.experiment_id.strip() or not self.git_commit.strip() or not self.code_version.strip():
            raise ValueError("experiment identity and code provenance are required")
        if not self.dataset_ids or any(not item.strip() for item in self.dataset_ids):
            raise ValueError("at least one stable dataset identifier is required")
        if len(set(self.dataset_ids)) != len(self.dataset_ids):
            raise ValueError("dataset identifiers must be unique")
        if self.random_seed < 0:
            raise ValueError("random_seed must be non-negative")
        if isinstance(self.embargo_seconds, bool) or not isinstance(self.embargo_seconds, int):
            raise ValueError("embargo_seconds must be an integer")
        if self.embargo_seconds < 0:
            raise ValueError("embargo_seconds must be non-negative")
        if not self.objectives or any(not item.strip() for item in self.objectives):
            raise ValueError("at least one explicitly named objective is required")
        if not self.cost_model_id.strip() or not self.execution_model_id.strip():
            raise ValueError("market-specific cost and execution model IDs are required")
        if self.compute_backend not in {"auto", "numpy", "cpu", "cupy"}:
            raise ValueError("compute_backend must be auto, numpy, cpu or cupy")
        if not self.compute_device.strip():
            raise ValueError("compute device provenance must be recorded")
        windows = (
            (self.training_start, self.training_end),
            (self.validation_start, self.validation_end),
            (self.oos_start, self.oos_end),
            (self.final_holdout_start, self.final_holdout_end),
        )
        for start, end in windows:
            if (start.tzinfo is None or start.utcoffset() is None
                    or end.tzinfo is None or end.utcoffset() is None):
                raise ValueError("experiment window timestamps must be timezone-aware")
            if end <= start:
                raise ValueError("each experiment window must have positive duration")
        embargo = timedelta(seconds=self.embargo_seconds)
        if not (
            self.training_end + embargo <= self.validation_start
            and self.validation_end + embargo <= self.oos_start
            and self.oos_end + embargo <= self.final_holdout_start
        ):
            raise ValueError(
                "experiment partitions must be chronological, non-overlapping and respect embargo"
            )

        # The old NSE 2024-2026 test set was exposed to prior strategy selection.
        # It cannot be relabelled as an untouched final holdout in the new platform.
        if self.market is Market.NSE:
            # The repository's prior protocol exposed TRAIN through 2023 and TEST through 2026-10-01.
            # No date inside either historical window may be relabelled as new OOS evidence.
            exposed_end = datetime(2026, 10, 1, 23, 59, 59, tzinfo=timezone.utc)
            if self.oos_start.astimezone(timezone.utc) <= exposed_end:
                raise ValueError(
                    "NSE OOS must begin after 2026-10-01; the historical TEST window is exposed"
                )
            if self.final_holdout_start.astimezone(timezone.utc) <= exposed_end:
                raise ValueError(
                    "NSE final holdout must begin after 2026-10-01; the historical test window is exposed"
                )
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        # Restrict parameters to finite JSON values so every configuration can be stored.
        try:
            json.dumps(self.parameters, sort_keys=True, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("experiment parameters must contain finite JSON-compatible values") from exc

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe experiment definition."""
        # Sort nested parameter keys so fingerprints are stable across runs.
        return {
            "experiment_id": self.experiment_id,
            "market": self.market.value,
            "initial_simulated_capital_inr": str(MARKET_SPECS[self.market].initial_simulated_capital),
            "track": self.track.value,
            "algorithm_family": self.algorithm_family.value,
            "resolution": self.resolution.value,
            "dataset_ids": list(self.dataset_ids),
            "random_seed": self.random_seed,
            "git_commit": self.git_commit,
            "code_version": self.code_version,
            "windows": {
                "training": [self.training_start.isoformat(), self.training_end.isoformat()],
                "validation": [self.validation_start.isoformat(), self.validation_end.isoformat()],
                "oos": [self.oos_start.isoformat(), self.oos_end.isoformat()],
                "final_holdout": [self.final_holdout_start.isoformat(), self.final_holdout_end.isoformat()],
            },
            "cost_model_id": self.cost_model_id,
            "execution_model_id": self.execution_model_id,
            "compute_backend": self.compute_backend,
            "compute_device": self.compute_device,
            "objectives": list(self.objectives),
            "parameters": self.parameters,
            "embargo_seconds": self.embargo_seconds,
            "created_at": self.created_at.astimezone(timezone.utc).isoformat(),
        }

    def validate_datasets(self, catalog: DataAvailabilityCatalog) -> None:
        """Reject missing or cross-market dataset references before a run starts."""
        # The market of every source dataset must match the experiment's isolated market.
        required_windows = (
            (self.training_start, self.training_end),
            (self.validation_start, self.validation_end),
            (self.oos_start, self.oos_end),
            (self.final_holdout_start, self.final_holdout_end),
        )
        for dataset_id in self.dataset_ids:
            manifest = catalog.get(dataset_id)
            if manifest.market is not self.market:
                raise ValueError(
                    f"cross-market dataset rejected: {dataset_id} belongs to {manifest.market.value}, "
                    f"not {self.market.value}"
                )
            if manifest.license_status.value != "approved":
                raise ValueError(
                    f"dataset {dataset_id} licence must be approved before research use"
                )
            # A dataset reference must cover every requested stage; missing coverage is not imputed.
            coverage_start = manifest.coverage_start.astimezone(timezone.utc)
            coverage_end = manifest.coverage_end.astimezone(timezone.utc)
            for window_start, window_end in required_windows:
                if coverage_start > window_start.astimezone(timezone.utc) or coverage_end < window_end.astimezone(timezone.utc):
                    raise ValueError(
                        f"dataset {dataset_id} does not cover window "
                        f"{window_start.isoformat()}..{window_end.isoformat()}"
                    )

    @property
    def fingerprint(self) -> str:
        """Hash all experiment-defining fields, including data and cost assumptions."""
        # Canonical JSON plus sorted keys makes experiment IDs auditable.
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
