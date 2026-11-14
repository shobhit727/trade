"""Dataset provenance manifests and an explicit data-availability catalogue."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from enum import StrEnum
from typing import TYPE_CHECKING, Iterable

from .domain import DataResolution, Market

if TYPE_CHECKING:
    import pandas as pd


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


_GAP_AUDIT_SCHEMA = "gap-audit-v1"

# Canonical observation cadence in seconds for resolutions the gap audit accepts.
# Weekly and monthly cadences are calendar-anchored rather than fixed-length, so
# an expected-bar count derived from a constant period would be a fabrication.
RESOLUTION_PERIOD_SECONDS: dict[str, int] = {
    DataResolution.ONE_SECOND.value: 1,
    DataResolution.ONE_MINUTE.value: 60,
    DataResolution.FIVE_MINUTES.value: 300,
    DataResolution.FIFTEEN_MINUTES.value: 900,
    DataResolution.THIRTY_MINUTES.value: 1800,
    DataResolution.ONE_HOUR.value: 3600,
    DataResolution.FOUR_HOURS.value: 14400,
    DataResolution.ONE_DAY.value: 86400,
}


def gap_audit(manifest: DatasetManifest, frame: "pd.DataFrame") -> dict[str, object]:
    """Audit observed bar coverage of ``frame`` against the manifest's declared cadence.

    Returns a structured record of measured facts only: first/last observation,
    expected-versus-actual bar count across the declared coverage window, and
    every missing interval longer than one declared resolution period with its
    start, end, length and absent-bar count. No quality grade, score or
    completeness label is inferred from these counts.

    The expected bar grid is half-open on ``[coverage_start, coverage_end)``
    anchored at ``coverage_start``, matching the platform's half-open boundary
    convention. Leading and trailing gap intervals span to the declared
    coverage endpoints; interior gap intervals span from the last observation
    before the gap to the first observation after it (half-open on
    ``[last_before, first_after)``, so the boundary bars are not themselves
    reported missing). The record is plain measured coverage; interpreting it
    (for example as exchange holidays or a provider outage) is a caller
    decision.
    """
    import pandas as pd

    if not isinstance(frame, pd.DataFrame):
        raise TypeError("gap audit requires a pandas DataFrame")
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError("gap audit requires a DatetimeIndex")
    if len(frame) == 0:
        raise ValueError("gap audit requires at least one observation")
    if frame.index.tz is None:
        raise ValueError("gap audit requires timezone-aware timestamps")
    if frame.index.has_duplicates:
        raise ValueError("gap audit requires unique timestamps")
    if not frame.index.is_monotonic_increasing:
        raise ValueError("gap audit requires chronologically ordered timestamps")

    period_seconds = RESOLUTION_PERIOD_SECONDS.get(manifest.resolution.value)
    if period_seconds is None:
        raise ValueError(
            f"gap audit supports fixed-cadence resolutions only; {manifest.resolution.value} "
            "is calendar-anchored and cannot yield an honest expected-bar count"
        )
    period = pd.Timedelta(seconds=period_seconds)

    observed = frame.index.tz_convert("UTC")
    first = observed[0]
    last = observed[-1]
    coverage_start = manifest.coverage_start.astimezone(timezone.utc)
    coverage_end = manifest.coverage_end.astimezone(timezone.utc)
    if first < coverage_start or last > coverage_end:
        raise ValueError(
            "frame observations extend beyond the manifest's declared coverage window"
        )
    expected_bars = int((coverage_end - coverage_start) // period)
    if expected_bars == 0:
        raise ValueError("declared coverage window is shorter than one resolution period")

    def _absent_slots(delta: pd.Timedelta) -> int:
        # Number of cadence slots a span covers, rounded up; a span of exactly
        # one period covers its own single slot.
        return int(-(-delta // period))

    gaps: list[dict[str, object]] = []

    # Absent slots between the declared coverage start and the first observation.
    leading = first - coverage_start
    if leading > pd.Timedelta(0):
        gaps.append({
            "start": coverage_start.isoformat(),
            "end": first.isoformat(),
            "length_seconds": leading.total_seconds(),
            "missing_bars": _absent_slots(leading),
        })

    # Interior intervals whose spacing exceeds one declared period. A spacing of
    # exactly one period is the declared cadence and is not a gap.
    deltas = observed[1:] - observed[:-1]
    for position in (i for i in range(len(deltas)) if deltas[i] > period):
        gap_start = observed[position]
        gap_end = observed[position + 1]
        span_delta = gap_end - gap_start
        gaps.append({
            "start": gap_start.isoformat(),
            "end": gap_end.isoformat(),
            "length_seconds": span_delta.total_seconds(),
            "missing_bars": _absent_slots(span_delta) - 1,
        })

    # Absent slots between the last observation and the declared coverage end;
    # the half-open window excludes a slot exactly at coverage_end.
    trailing = coverage_end - last
    if _absent_slots(trailing) > 1:
        gaps.append({
            "start": last.isoformat(),
            "end": coverage_end.isoformat(),
            "length_seconds": trailing.total_seconds(),
            "missing_bars": _absent_slots(trailing) - 1,
        })

    record: dict[str, object] = {
        "schema": _GAP_AUDIT_SCHEMA,
        "resolution": manifest.resolution.value,
        "period_seconds": period_seconds,
        "coverage_start": coverage_start.isoformat(),
        "coverage_end": coverage_end.isoformat(),
        "first_observation": first.isoformat(),
        "last_observation": last.isoformat(),
        "expected_bars": expected_bars,
        "actual_bars": int(len(frame)),
        "gap_count": len(gaps),
        "missing_bars_total": sum(int(gap["missing_bars"]) for gap in gaps),
        "gaps": gaps,
    }
    return record


def manifest_with_gap_audit(manifest: DatasetManifest, frame: "pd.DataFrame") -> DatasetManifest:
    """Return a manifest copy whose extra_metadata carries the canonical gap audit.

    Follows the adapters' quality-report idiom: the audit record is serialised
    as canonical JSON (sorted keys, compact separators) under a fixed key. The
    source manifest is immutable, so the audited copy replaces it in callers'
    catalogues; its fingerprint changes with the added metadata.
    """
    record = gap_audit(manifest, frame)
    extra = dict(manifest.extra_metadata)
    extra["gap_audit_json"] = json.dumps(
        record, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return replace(manifest, extra_metadata=extra)


def utc_timestamp(value: datetime) -> datetime:
    """Normalise an aware timestamp to UTC for persisted provenance."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)
