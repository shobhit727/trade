"""Dataset provenance manifests and an explicit data-availability catalogue."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Iterable

from .domain import DataResolution, Market


class ValueOrigin(StrEnum):
    """Distinguishes observations from transformations and inferred values."""

    OBSERVED = "observed"
    ADJUSTED = "adjusted"
    DERIVED = "derived"
    RECONSTRUCTED = "reconstructed"
    ESTIMATED = "estimated"
    INTERPOLATED = "interpolated"


class LicenseStatus(StrEnum):
    """License review state; unreviewed sources cannot be silently treated as open."""

    APPROVED = "approved"
    RESTRICTED = "restricted"
    REVIEW_REQUIRED = "review_required"
    PROHIBITED = "prohibited"


@dataclass(frozen=True, slots=True)
class TimeGap:
    """Known missing-data interval, with timezone-aware UTC endpoints."""

    start: datetime
    end: datetime
    reason: str

    def __post_init__(self) -> None:
        # Enforce ordered, timezone-aware gap boundaries.
        for value in (self.start, self.end):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("gap timestamps must be timezone-aware")
        if self.end <= self.start or not self.reason.strip():
            raise ValueError("gap end must follow start and reason must be supplied")


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    """Immutable provenance record for a market dataset or derived dataset."""

    dataset_id: str
    market: Market
    provider: str
    source: str
    instrument: str
    exchange: str
    category: str
    resolution: DataResolution
    coverage_start: datetime
    coverage_end: datetime
    timezone: str
    timestamp_convention: str
    acquired_at: datetime
    update_frequency: str
    license_status: LicenseStatus
    license_reference: str
    value_origin: ValueOrigin = ValueOrigin.OBSERVED
    quality_score: float | None = None
    known_gaps: tuple[TimeGap, ...] = ()
    adjustment_method: str = "none"
    processing_history: tuple[str, ...] = ()
    schema_version: str = "1"
    extra_metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validate identity, coverage, timestamps, licensing and quality metadata.
        required = (self.dataset_id, self.provider, self.source, self.instrument,
                    self.exchange, self.category, self.timezone,
                    self.timestamp_convention, self.update_frequency, self.license_reference)
        if any(not item.strip() for item in required):
            raise ValueError("dataset identity and provenance fields must be non-empty")
        for value in (self.coverage_start, self.coverage_end, self.acquired_at):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("dataset timestamps must be timezone-aware")
        if self.coverage_end < self.coverage_start:
            raise ValueError("coverage_end cannot precede coverage_start")
        if self.quality_score is not None and not 0.0 <= self.quality_score <= 1.0:
            raise ValueError("quality_score must be between 0 and 1")
        if self.license_status is LicenseStatus.APPROVED and self.license_reference == "unknown":
            raise ValueError("approved licensing requires a traceable license reference")
        if any(not isinstance(key, str) or not isinstance(value, str)
               for key, value in self.extra_metadata.items()):
            raise ValueError("extra_metadata must contain string keys and values")

    def to_dict(self) -> dict[str, object]:
        """Convert all metadata into a JSON-safe, stable representation."""
        # Convert enums, tuples and datetimes explicitly for portable manifests.
        data = asdict(self)
        data["market"] = self.market.value
        data["resolution"] = self.resolution.value
        data["license_status"] = self.license_status.value
        data["value_origin"] = self.value_origin.value
        for key in ("coverage_start", "coverage_end", "acquired_at"):
            data[key] = getattr(self, key).astimezone(timezone.utc).isoformat()
        data["known_gaps"] = [
            {
                "start": gap.start.astimezone(timezone.utc).isoformat(),
                "end": gap.end.astimezone(timezone.utc).isoformat(),
                "reason": gap.reason,
            }
            for gap in self.known_gaps
        ]
        return data

    @property
    def fingerprint(self) -> str:
        """SHA-256 fingerprint of the canonical provenance record."""
        # Canonical JSON keeps the same manifest hash across process and key ordering.
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class DataAvailabilityCatalog:
    """In-memory registry that rejects silent replacement of dataset identifiers."""

    def __init__(self, manifests: Iterable[DatasetManifest] = ()) -> None:
        # Build through register() so constructor input receives the same validation.
        self._manifests: dict[str, DatasetManifest] = {}
        for manifest in manifests:
            self.register(manifest)

    def register(self, manifest: DatasetManifest) -> None:
        """Register one unique immutable dataset manifest."""
        existing = self._manifests.get(manifest.dataset_id)
        if existing is not None and existing.fingerprint != manifest.fingerprint:
            raise ValueError(f"dataset_id already exists with different metadata: {manifest.dataset_id}")
        self._manifests[manifest.dataset_id] = manifest

    def get(self, dataset_id: str) -> DatasetManifest:
        """Fetch a manifest by stable dataset identifier."""
        return self._manifests[dataset_id]

    def query(
        self,
        *,
        market: Market | None = None,
        exchange: str | None = None,
        resolution: DataResolution | None = None,
        category: str | None = None,
        approved_only: bool = False,
    ) -> tuple[DatasetManifest, ...]:
        """Return matching manifests without conflating unavailable coverage."""
        # Every filter is an exact metadata filter; this method does not imply data exists.
        matches = []
        for item in self._manifests.values():
            if market is not None and item.market is not market:
                continue
            if exchange is not None and item.exchange != exchange:
                continue
            if resolution is not None and item.resolution is not resolution:
                continue
            if category is not None and item.category != category:
                continue
            if approved_only and item.license_status is not LicenseStatus.APPROVED:
                continue
            matches.append(item)
        return tuple(sorted(matches, key=lambda row: row.dataset_id))

    def availability_matrix(self) -> dict[str, dict[str, int]]:
        """Summarise registered datasets by market, exchange and resolution."""
        # Counts describe catalogued manifests, not total assets or full market coverage.
        matrix: dict[str, dict[str, int]] = {}
        for item in self._manifests.values():
            key = f"{item.market.value}:{item.exchange}"
            matrix.setdefault(key, {})[item.resolution.value] = (
                matrix.setdefault(key, {}).get(item.resolution.value, 0) + 1
            )
        return matrix


def utc_timestamp(value: datetime) -> datetime:
    """Normalise an aware timestamp to UTC for persisted provenance."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)
