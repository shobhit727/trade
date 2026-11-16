"""SQLite-backed append-only experiment and evolutionary-lineage registry."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import statistics
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from .data_catalog import DatasetManifest
from .experiments import ExperimentSpec


def _advance_validation_lifecycle(
    state: dict[str, Any],
    transition: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Validate one lifecycle transition and return its next durable state."""
    # State changes are reduced while SQLite holds a write lock, preventing duplicate access.
    current = state["state"]
    updated = dict(state)
    if transition == "candidate_frozen":
        digest = payload.get("candidate_digest")
        if current != "discovery":
            raise RuntimeError("candidate can only be frozen once during discovery")
        if not isinstance(digest, str) or len(digest) < 16:
            raise ValueError("candidate_digest must be a stable cryptographic fingerprint")
        updated.update(state="candidate_frozen", candidate_digest=digest)
    elif transition == "oos_evaluation_started":
        if current != "candidate_frozen":
            raise PermissionError("OOS evaluation is permitted once after candidate freeze")
        if payload.get("candidate_digest") != state.get("candidate_digest"):
            raise PermissionError("OOS candidate digest does not match the frozen candidate")
        updated["state"] = "oos_evaluating"
    elif transition == "oos_recorded":
        evaluation_id = payload.get("evaluation_id")
        passed = payload.get("passed")
        if current != "oos_evaluating":
            raise RuntimeError("OOS result requires the single authorised OOS evaluation")
        if not isinstance(evaluation_id, str) or not evaluation_id.strip():
            raise ValueError("evaluation_id is required")
        if passed is not None and not isinstance(passed, bool):
            raise ValueError("passed must be true, false or null when no OOS gate is defined")
        updated.update(state="oos_recorded", oos_evaluation_id=evaluation_id, oos_passed=passed)
    elif transition == "holdout_opened":
        approval = payload.get("approval_reference")
        if current != "oos_recorded" or state.get("oos_passed") is not True:
            raise PermissionError("final holdout requires a passing recorded OOS evaluation")
        if not isinstance(approval, str) or not approval.strip():
            raise PermissionError("holdout approval must be supplied once")
        updated["state"] = "holdout_opened"
    elif transition == "holdout_accessed":
        if current != "holdout_opened":
            raise PermissionError("final holdout is sealed until explicitly unlocked")
        if int(state.get("holdout_access_count", 0)) != 0:
            raise PermissionError("final holdout data may be opened only once")
        updated["holdout_access_count"] = 1
    elif transition == "holdout_access_refused":
        # Repeated-access refusals are recorded without changing the durable state.
        if current != "holdout_opened" or int(state.get("holdout_access_count", 0)) == 0:
            raise PermissionError("final holdout is sealed until explicitly unlocked")
    elif transition == "completed":
        if current != "holdout_opened" or int(state.get("holdout_access_count", 0)) != 1:
            raise RuntimeError("lifecycle requires one final holdout review")
        updated["state"] = "completed"
    else:
        raise ValueError(f"unknown validation lifecycle transition: {transition}")
    return updated


def _reduce_validation_lifecycle(
    rows: list[sqlite3.Row],
    lifecycle_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Reconstruct one job's lifecycle from its append-only event history."""
    # A lifecycle ID is the persistent job ID; independent reruns have independent histories.
    state: dict[str, Any] = {
        "state": "discovery",
        "candidate_digest": None,
        "oos_passed": None,
        "oos_evaluation_id": None,
        "holdout_access_count": 0,
    }
    events: list[dict[str, Any]] = []
    prefix = "validation_lifecycle_"
    for row in rows:
        event_type = str(row["event_type"])
        if not event_type.startswith(prefix):
            continue
        payload = json.loads(row["payload_json"])
        if payload.get("lifecycle_id") != lifecycle_id:
            continue
        transition = event_type.removeprefix(prefix)
        state = _advance_validation_lifecycle(state, transition, payload)
        events.append({
            "event": transition,
            "occurred_at": row["occurred_at"],
            "payload": payload,
        })
    return state, events

LICENCE_APPROVAL_EVENT = "dataset_licence_approved"


def _apply_licence_decision(
    manifest: dict[str, Any],
    event: sqlite3.Row | None,
) -> dict[str, Any]:
    """Overlay the latest append-only licence decision onto a parsed manifest copy."""
    # Registered manifests stay immutable; review state derives from the event stream.
    if event is None or event["event_type"] != LICENCE_APPROVAL_EVENT:
        return manifest
    payload = json.loads(event["payload_json"])
    manifest["license_status"] = "approved"
    manifest["license_reference"] = str(
        payload.get("licence_reference") or manifest.get("license_reference", "")
    )
    manifest["licence_reviewed_by"] = str(payload.get("reviewed_by") or "")
    manifest["licence_decision"] = str(payload.get("decision") or "")
    manifest["licence_decided_at"] = event["occurred_at"]
    return manifest


class ExperimentStore:
    """Persist immutable experiment definitions, events and candidate lineage."""

    def __init__(self, database_path: str | Path) -> None:
        # Use a dedicated research database; do not share trading account state tables.
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        # Every connection enables referential integrity and a bounded lock wait.
        connection = sqlite3.connect(self.database_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        # Explicitly close connections after committing or rolling back each transaction.
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialise(self) -> None:
        # WAL allows concurrent readers while a worker appends experiment records.
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS experiments (
                    experiment_id TEXT PRIMARY KEY,
                    market TEXT NOT NULL CHECK (market IN ('nse', 'crypto')),
                    track TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    spec_json TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS immutable_experiments_update
                BEFORE UPDATE ON experiments BEGIN
                    SELECT RAISE(ABORT, 'experiment definitions are immutable');
                END;
                CREATE TRIGGER IF NOT EXISTS immutable_experiments_delete
                BEFORE DELETE ON experiments BEGIN
                    SELECT RAISE(ABORT, 'experiment definitions are immutable');
                END;
                CREATE TABLE IF NOT EXISTS experiment_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
                    event_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_events_experiment
                    ON experiment_events(experiment_id, event_id);
                CREATE TABLE IF NOT EXISTS candidates (
                    candidate_id TEXT PRIMARY KEY,
                    experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
                    candidate_digest TEXT NOT NULL,
                    family TEXT NOT NULL,
                    generation INTEGER NOT NULL CHECK (generation >= 0),
                    parameters_json TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    lineage_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(experiment_id, candidate_digest)
                );
                CREATE TABLE IF NOT EXISTS datasets (
                    dataset_id TEXT PRIMARY KEY,
                    market TEXT NOT NULL CHECK (market IN ('nse', 'crypto')),
                    exchange TEXT NOT NULL,
                    resolution TEXT NOT NULL,
                    category TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    registered_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_datasets_market
                    ON datasets(market, exchange, resolution);
                CREATE TRIGGER IF NOT EXISTS immutable_datasets_update
                BEFORE UPDATE ON datasets BEGIN
                    SELECT RAISE(ABORT, 'dataset manifests are immutable');
                END;
                CREATE TRIGGER IF NOT EXISTS immutable_datasets_delete
                BEFORE DELETE ON datasets BEGIN
                    SELECT RAISE(ABORT, 'dataset manifests are immutable');
                END;
                CREATE INDEX IF NOT EXISTS idx_candidates_experiment
                    ON candidates(experiment_id, generation);
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
                    runner_name TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (
                        status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')
                    ),
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    parameters_json TEXT NOT NULL,
                    result_json TEXT,
                    error_message TEXT,
                    lease_owner TEXT,
                    lease_expires_at TEXT,
                    lease_token TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_lease_expiry
                    ON jobs(lease_expires_at);
                CREATE INDEX IF NOT EXISTS idx_jobs_experiment
                    ON jobs(experiment_id, created_at);
                CREATE TABLE IF NOT EXISTS job_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL REFERENCES jobs(job_id),
                    event_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_job_events_job
                    ON job_events(job_id, event_id);
                CREATE TABLE IF NOT EXISTS job_checkpoints (
                    checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL REFERENCES jobs(job_id),
                    created_at TEXT NOT NULL,
                    progress_json TEXT NOT NULL,
                    random_state_json TEXT,
                    candidates_json TEXT NOT NULL,
                    environment_json TEXT,
                    integrity_digest TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_job_checkpoints_job
                    ON job_checkpoints(job_id, checkpoint_id);
                CREATE TRIGGER IF NOT EXISTS immutable_job_checkpoints_update
                BEFORE UPDATE ON job_checkpoints BEGIN
                    SELECT RAISE(ABORT, 'job checkpoints are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS immutable_job_checkpoints_delete
                BEFORE DELETE ON job_checkpoints BEGIN
                    SELECT RAISE(ABORT, 'job checkpoints are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS immutable_job_events_update
                BEFORE UPDATE ON job_events BEGIN
                    SELECT RAISE(ABORT, 'job events are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS immutable_job_events_delete
                BEFORE DELETE ON job_events BEGIN
                    SELECT RAISE(ABORT, 'job events are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS immutable_events_update
                BEFORE UPDATE ON experiment_events BEGIN
                    SELECT RAISE(ABORT, 'experiment events are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS immutable_events_delete
                BEFORE DELETE ON experiment_events BEGIN
                    SELECT RAISE(ABORT, 'experiment events are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS immutable_candidates_update
                BEFORE UPDATE ON candidates BEGIN
                    SELECT RAISE(ABORT, 'candidate records are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS immutable_candidates_delete
                BEFORE DELETE ON candidates BEGIN
                    SELECT RAISE(ABORT, 'candidate records are append-only');
                END;
                CREATE TABLE IF NOT EXISTS dataset_licence_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
                    event_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_dataset_licence_events_dataset
                    ON dataset_licence_events(dataset_id, event_id);
                CREATE TRIGGER IF NOT EXISTS immutable_dataset_licence_events_update
                BEFORE UPDATE ON dataset_licence_events BEGIN
                    SELECT RAISE(ABORT, 'dataset licence events are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS immutable_dataset_licence_events_delete
                BEFORE DELETE ON dataset_licence_events BEGIN
                    SELECT RAISE(ABORT, 'dataset licence events are append-only');
                END;
                """
            )
            self._migrate_job_lease_columns(connection)

    def _migrate_job_lease_columns(self, connection: sqlite3.Connection) -> None:
        """Add lease columns to jobs rows created before worker leases existed."""
        # Additive migration: existing databases gain nullable lease columns;
        # fresh databases already carry them from the DDL above.
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(jobs)").fetchall()
        }
        for column, definition in (
            ("lease_owner", "TEXT"),
            ("lease_expires_at", "TEXT"),
            ("lease_token", "TEXT"),
        ):
            if column not in columns:
                connection.execute(
                    f"ALTER TABLE jobs ADD COLUMN {column} {definition}"
                )

    def create_experiment(self, spec: ExperimentSpec) -> None:
        """Persist an immutable, market-scoped experiment definition."""
        # Exact config and fingerprints are stored together for later reproducibility checks.
        payload = json.dumps(spec.to_dict(), sort_keys=True, separators=(",", ":"))
        with self._connection() as connection:
            connection.execute(
                """INSERT INTO experiments
                   (experiment_id, market, track, created_at, fingerprint, spec_json)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (spec.experiment_id, spec.market.value, spec.track.value,
                 spec.created_at.astimezone(timezone.utc).isoformat(), spec.fingerprint, payload),
            )

    def append_event(self, experiment_id: str, event_type: str, payload: dict[str, Any]) -> int:
        """Append an immutable lifecycle/progress event and return its row identifier."""
        # JSON is canonicalised and NaN/Infinity are rejected to keep logs parseable.
        if not event_type.strip():
            raise ValueError("event_type must be non-empty")
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        with self._connection() as connection:
            cursor = connection.execute(
                """INSERT INTO experiment_events
                   (experiment_id, event_type, occurred_at, payload_json)
                   VALUES (?, ?, ?, ?)""",
                (experiment_id, event_type, datetime.now(timezone.utc).isoformat(), encoded),
            )
            return int(cursor.lastrowid)

    def transition_validation_lifecycle(
        self,
        experiment_id: str,
        lifecycle_id: str,
        transition: str,
        payload: dict[str, Any],
    ) -> int:
        """Atomically append one validated, job-scoped lifecycle transition."""
        # BEGIN IMMEDIATE serializes reduction and insertion across store instances/processes.
        if not lifecycle_id.strip() or len(lifecycle_id) > 200:
            raise ValueError("lifecycle_id must contain 1..200 non-whitespace characters")
        if not isinstance(payload, dict):
            raise TypeError("validation lifecycle payload must be a dictionary")
        if "lifecycle_id" in payload and payload["lifecycle_id"] != lifecycle_id:
            raise ValueError("payload lifecycle_id cannot override the lifecycle key")
        event_payload = {**payload, "lifecycle_id": lifecycle_id}
        encoded = json.dumps(
            event_payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """SELECT event_type, occurred_at, payload_json
                   FROM experiment_events
                   WHERE experiment_id = ? AND event_type LIKE 'validation_lifecycle_%'
                   ORDER BY event_id""",
                (experiment_id,),
            ).fetchall()
            state, _ = _reduce_validation_lifecycle(rows, lifecycle_id)
            _advance_validation_lifecycle(state, transition, event_payload)
            cursor = connection.execute(
                """INSERT INTO experiment_events
                   (experiment_id, event_type, occurred_at, payload_json)
                   VALUES (?, ?, ?, ?)""",
                (
                    experiment_id,
                    f"validation_lifecycle_{transition}",
                    datetime.now(timezone.utc).isoformat(),
                    encoded,
                ),
            )
            return int(cursor.lastrowid)

    def get_validation_lifecycle(
        self,
        experiment_id: str,
        lifecycle_id: str,
    ) -> dict[str, Any]:
        """Rebuild one durable validation lifecycle from append-only experiment events."""
        # No mutable snapshot is trusted; the state is derived from the event stream.
        if not lifecycle_id.strip() or len(lifecycle_id) > 200:
            raise ValueError("lifecycle_id must contain 1..200 non-whitespace characters")
        with self._connection() as connection:
            exists = connection.execute(
                "SELECT 1 FROM experiments WHERE experiment_id = ?",
                (experiment_id,),
            ).fetchone()
            if exists is None:
                raise KeyError(experiment_id)
            rows = connection.execute(
                """SELECT event_type, occurred_at, payload_json
                   FROM experiment_events
                   WHERE experiment_id = ? AND event_type LIKE 'validation_lifecycle_%'
                   ORDER BY event_id""",
                (experiment_id,),
            ).fetchall()
        state, events = _reduce_validation_lifecycle(rows, lifecycle_id)
        return {"lifecycle_id": lifecycle_id, **state, "events": tuple(events)}

    def has_candidate(self, experiment_id: str, candidate_digest: str) -> bool:
        """Return whether an immutable candidate fingerprint is already recorded."""
        # Duplicate evaluations may reference an existing candidate without overwriting it.
        with self._connection() as connection:
            row = connection.execute(
                """SELECT 1 FROM candidates
                   WHERE experiment_id = ? AND candidate_digest = ? LIMIT 1""",
                (experiment_id, candidate_digest),
            ).fetchone()
        return row is not None

    def append_candidate(
        self,
        *,
        candidate_id: str,
        experiment_id: str,
        candidate_digest: str,
        family: str,
        generation: int,
        parameters: dict[str, Any],
        metrics: dict[str, Any],
        lineage: dict[str, Any],
    ) -> None:
        """Persist one candidate and its parent/mutation/crossover lineage."""
        # Metrics may contain JSON numbers only; reject non-finite values rather than hiding them.
        if generation < 0 or not candidate_id.strip() or len(candidate_digest) < 16:
            raise ValueError("candidate identity, digest and non-negative generation are required")
        values = [json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
                  for value in (parameters, metrics, lineage)]
        with self._connection() as connection:
            connection.execute(
                """INSERT INTO candidates
                   (candidate_id, experiment_id, candidate_digest, family, generation,
                    parameters_json, metrics_json, lineage_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (candidate_id, experiment_id, candidate_digest, family, generation,
                 *values, datetime.now(timezone.utc).isoformat()),
            )

    def events(self, experiment_id: str) -> tuple[dict[str, Any], ...]:
        """Read experiment history in append order."""
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM experiment_events WHERE experiment_id = ? ORDER BY event_id",
                (experiment_id,),
            ).fetchall()
        return tuple({**dict(row), "payload": json.loads(row["payload_json"])} for row in rows)

    def candidates(self, experiment_id: str) -> tuple[dict[str, Any], ...]:
        """Read candidate definitions and fitness records in generation order."""
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM candidates WHERE experiment_id = ? ORDER BY generation, candidate_id",
                (experiment_id,),
            ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            for field in ("parameters_json", "metrics_json", "lineage_json"):
                item[field.removesuffix("_json")] = json.loads(item[field])
            output.append(item)
        return tuple(output)

    def get_experiment(self, experiment_id: str) -> dict[str, Any]:
        """Return the immutable experiment specification and its fingerprint."""
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM experiments WHERE experiment_id = ?", (experiment_id,)
            ).fetchone()
        if row is None:
            raise KeyError(experiment_id)
        result = dict(row)
        result["spec"] = json.loads(result.pop("spec_json"))
        return result


    def list_experiments(
        self, *, market: str | None = None, limit: int = 100
    ) -> tuple[dict[str, Any], ...]:
        """List experiment metadata, optionally restricted to one financial environment."""
        # Bound result size and validate the market filter to avoid an unbounded dashboard query.
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        if market is not None and market not in {"nse", "crypto"}:
            raise ValueError("market must be 'nse' or 'crypto'")
        with self._connection() as connection:
            if market is None:
                rows = connection.execute(
                    """SELECT experiment_id, market, track, created_at, fingerprint
                       FROM experiments ORDER BY created_at DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """SELECT experiment_id, market, track, created_at, fingerprint
                       FROM experiments WHERE market = ? ORDER BY created_at DESC LIMIT ?""",
                    (market, limit),
                ).fetchall()
        # Return independent market-scoped rows; no aggregate capital or return is computed.
        return tuple(dict(row) for row in rows)


    def register_dataset(self, manifest: DatasetManifest) -> None:
        """Persist an immutable dataset provenance manifest."""
        # Source file bytes are not copied into SQLite; the manifest references their checksum.
        payload = json.dumps(manifest.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False)
        with self._connection() as connection:
            connection.execute(
                """INSERT INTO datasets
                   (dataset_id, market, exchange, resolution, category, fingerprint,
                    manifest_json, registered_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    manifest.dataset_id,
                    manifest.market.value,
                    manifest.exchange,
                    manifest.resolution.value,
                    manifest.category,
                    manifest.fingerprint,
                    payload,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def get_dataset(self, dataset_id: str) -> dict[str, Any]:
        """Return a persisted manifest and its immutable fingerprint."""
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM datasets WHERE dataset_id = ?", (dataset_id,)
            ).fetchone()
            if row is None:
                raise KeyError(dataset_id)
            event = connection.execute(
                """SELECT event_type, occurred_at, payload_json
                   FROM dataset_licence_events WHERE dataset_id = ?
                   ORDER BY event_id DESC LIMIT 1""",
                (dataset_id,),
            ).fetchone()
        result = dict(row)
        manifest = json.loads(result.pop("manifest_json"))
        result["manifest"] = _apply_licence_decision(manifest, event)
        return result

    def list_datasets(
        self, *, market: str | None = None, limit: int = 1000
    ) -> tuple[dict[str, Any], ...]:
        """List market-scoped dataset coverage and licence metadata."""
        # Bound dashboard queries and prevent accidental combined financial coverage views.
        if not 1 <= limit <= 5000:
            raise ValueError("limit must be between 1 and 5000")
        if market is not None and market not in {"nse", "crypto"}:
            raise ValueError("market must be 'nse' or 'crypto'")
        with self._connection() as connection:
            if market is None:
                rows = connection.execute(
                    """SELECT dataset_id, market, exchange, resolution, category,
                              fingerprint, manifest_json, registered_at
                       FROM datasets ORDER BY market, exchange, dataset_id LIMIT ?""",
                    (limit,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """SELECT dataset_id, market, exchange, resolution, category,
                              fingerprint, manifest_json, registered_at
                       FROM datasets WHERE market = ?
                       ORDER BY exchange, dataset_id LIMIT ?""",
                    (market, limit),
                ).fetchall()
            # Latest licence decision per dataset keeps dashboard listings current.
            licence_events = {
                str(event_row["dataset_id"]): event_row
                for event_row in connection.execute(
                    """SELECT e.dataset_id, e.event_type, e.occurred_at, e.payload_json
                       FROM dataset_licence_events AS e
                       JOIN (
                           SELECT dataset_id, MAX(event_id) AS event_id
                           FROM dataset_licence_events GROUP BY dataset_id
                       ) AS latest ON latest.dataset_id = e.dataset_id
                                  AND latest.event_id = e.event_id"""
                ).fetchall()
            }
        output = []
        for row in rows:
            # Surface metadata already registered with the immutable dataset manifest.
            item = dict(row)
            manifest = _apply_licence_decision(
                json.loads(item.pop("manifest_json")),
                licence_events.get(str(item["dataset_id"])),
            )
            # Expose the source coverage and the actual worker-visible partition separately.
            extra = manifest.get("extra_metadata", {})
            partitioned = bool(extra.get("research_partition_path"))
            item.update({
                "provider": manifest["provider"],
                "source": manifest["source"],
                "coverage_start": manifest["coverage_start"],
                "coverage_end": manifest["coverage_end"],
                "worker_coverage_start": (
                    extra.get("research_partition_coverage_start")
                    if partitioned else manifest["coverage_start"]
                ),
                "worker_coverage_end": (
                    extra.get("research_partition_coverage_end")
                    if partitioned else manifest["coverage_end"]
                ),
                "partitioned_non_holdout": partitioned,
                "timezone": manifest["timezone"],
                "license_status": manifest["license_status"],
                "license_reference": manifest["license_reference"],
                "licence_reviewed_by": manifest.get("licence_reviewed_by"),
                "licence_decided_at": manifest.get("licence_decided_at"),
                "quality_score": manifest.get("quality_score"),
                "known_gap_count": len(manifest.get("known_gaps", [])),
                "update_frequency": manifest["update_frequency"],
                "value_origin": manifest["value_origin"],
            })
            output.append(item)
        return tuple(output)


    def create_job(
        self,
        *,
        job_id: str,
        experiment_id: str,
        runner_name: str,
        parameters: dict[str, Any],
    ) -> None:
        """Persist a queued research job against an existing experiment."""
        # Jobs reference a fixed runner name; no executable source is accepted.
        if not job_id.strip() or not runner_name.strip():
            raise ValueError("job_id and runner_name must be non-empty")
        encoded = json.dumps(parameters, sort_keys=True, separators=(",", ":"), allow_nan=False)
        with self._connection() as connection:
            connection.execute(
                """INSERT INTO jobs
                   (job_id, experiment_id, runner_name, status, created_at, parameters_json)
                   VALUES (?, ?, ?, 'queued', ?, ?)""",
                (job_id, experiment_id, runner_name, datetime.now(timezone.utc).isoformat(), encoded),
            )

    def update_job_status(
        self,
        job_id: str,
        status: str,
        *,
        result: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        """Apply a legal job-state transition and persist its terminal summary."""
        # Reject status rewrites and impossible lifecycle transitions.
        allowed = {
            "queued": {"running", "failed", "cancelled"},
            "running": {"succeeded", "failed", "cancelled"},
            "succeeded": set(),
            "failed": set(),
            "cancelled": set(),
        }
        if status not in allowed:
            raise ValueError(f"unknown job status: {status}")
        encoded = None if result is None else json.dumps(
            result, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        with self._connection() as connection:
            row = connection.execute(
                "SELECT status FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if row is None:
                raise KeyError(job_id)
            current = row["status"]
            if status not in allowed[current]:
                raise ValueError(f"invalid job transition: {current} -> {status}")
            started_at = datetime.now(timezone.utc).isoformat() if status == "running" else None
            completed_at = (
                datetime.now(timezone.utc).isoformat()
                if status in {"succeeded", "failed", "cancelled"} else None
            )
            connection.execute(
                """UPDATE jobs
                   SET status = ?,
                       started_at = COALESCE(?, started_at),
                       completed_at = COALESCE(?, completed_at),
                       result_json = COALESCE(?, result_json),
                       error_message = ?
                   WHERE job_id = ?""",
                (status, started_at, completed_at, encoded, error_message, job_id),
            )

    def append_job_event(self, job_id: str, event_type: str, payload: dict[str, Any]) -> int:
        """Append a job lifecycle/progress event."""
        # Events are immutable so failures and cancellation requests remain auditable.
        if not event_type.strip():
            raise ValueError("event_type must be non-empty")
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        with self._connection() as connection:
            cursor = connection.execute(
                """INSERT INTO job_events (job_id, event_type, occurred_at, payload_json)
                   VALUES (?, ?, ?, ?)""",
                (job_id, event_type, datetime.now(timezone.utc).isoformat(), encoded),
            )
            return int(cursor.lastrowid)

    def append_dataset_licence_event(
        self, dataset_id: str, event_type: str, payload: dict[str, Any]
    ) -> int:
        """Append an immutable licence-review event for a registered dataset."""
        # Mirrors the append-only job/experiment event idiom; registered manifests
        # and their fingerprints are never rewritten by a licence decision.
        if not event_type.strip():
            raise ValueError("event_type must be non-empty")
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        with self._connection() as connection:
            cursor = connection.execute(
                """INSERT INTO dataset_licence_events
                   (dataset_id, event_type, occurred_at, payload_json)
                   VALUES (?, ?, ?, ?)""",
                (dataset_id, event_type, datetime.now(timezone.utc).isoformat(), encoded),
            )
            return int(cursor.lastrowid)

    def dataset_licence_events(self, dataset_id: str) -> tuple[dict[str, Any], ...]:
        """Read one dataset's licence review history in append order."""
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM dataset_licence_events WHERE dataset_id = ? ORDER BY event_id",
                (dataset_id,),
            ).fetchall()
        return tuple({**dict(row), "payload": json.loads(row["payload_json"])} for row in rows)

    def get_job(self, job_id: str) -> dict[str, Any]:
        """Return persisted job status, parameters, result and ordered events."""
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            events = connection.execute(
                "SELECT * FROM job_events WHERE job_id = ? ORDER BY event_id", (job_id,)
            ).fetchall()
        result = dict(row)
        result["parameters"] = json.loads(result.pop("parameters_json"))
        if result["result_json"] is not None:
            result["result"] = json.loads(result.pop("result_json"))
        else:
            result.pop("result_json")
            result["result"] = None
        result["events"] = [
            {**dict(event), "payload": json.loads(event["payload_json"])}
            for event in events
        ]
        return result

    def recover_interrupted_jobs(self) -> int:
        """Mark queued/running jobs from a previous process as failed and auditable."""
        # ThreadPoolExecutor work is not durable across process death; never imply it resumed.
        now = datetime.now(timezone.utc).isoformat()
        reason = "worker process restarted; job was interrupted and must be resubmitted"
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT job_id, status FROM jobs WHERE status IN ('queued', 'running')"
            ).fetchall()
            for row in rows:
                connection.execute(
                    """UPDATE jobs
                       SET status = 'failed', completed_at = ?, error_message = ?
                       WHERE job_id = ? AND status IN ('queued', 'running')""",
                    (now, reason, row["job_id"]),
                )
                connection.execute(
                    """INSERT INTO job_events
                       (job_id, event_type, occurred_at, payload_json)
                       VALUES (?, 'job_interrupted_on_restart', ?, ?)""",
                    (
                        row["job_id"],
                        now,
                        json.dumps({"previous_status": row["status"], "reason": reason},
                                   sort_keys=True, separators=(",", ":")),
                    ),
                )
        return len(rows)

    def list_jobs(
        self, *, experiment_id: str | None = None, limit: int = 100
    ) -> tuple[dict[str, Any], ...]:
        """List jobs without combining market P&L or portfolio state."""
        # Keep API/dashboard listings bounded.
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        with self._connection() as connection:
            if experiment_id is None:
                rows = connection.execute(
                    """SELECT job_id, experiment_id, runner_name, status,
                              created_at, started_at, completed_at, error_message
                       FROM jobs ORDER BY created_at DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """SELECT job_id, experiment_id, runner_name, status,
                              created_at, started_at, completed_at, error_message
                       FROM jobs WHERE experiment_id = ? ORDER BY created_at DESC LIMIT ?""",
                    (experiment_id, limit),
                ).fetchall()
        return tuple(dict(row) for row in rows)

    def export_experiment(self, experiment_id: str) -> dict[str, Any]:
        """Assemble the complete offline-analysis bundle for one experiment (audit F-033)."""
        # Every record type comes from the same stored rows the API serves; nothing
        # is recomputed, so an offline consumer sees exactly what the platform saw.
        experiment = self.get_experiment(experiment_id)
        events = self.events(experiment_id)
        candidates = self.candidates(experiment_id)
        environments = [
            {**event["payload"], "_occurred_at": event["occurred_at"]}
            for event in events
            if event["event_type"] == "environment_recorded"
        ]
        # Any event payload may carry an OOS acceptance verdict under the approved
        # policy; collecting by key keeps verdicts auditable regardless of which
        # runner event type recorded them (suffix-based collection would drop the
        # existing-strategy path's existing_strategy_evaluated records).
        oos_acceptances = [
            {**event["payload"], "_occurred_at": event["occurred_at"]}
            for event in events
            if isinstance(event["payload"], dict) and "oos_acceptance" in event["payload"]
        ]
        classification_reports = [
            {
                "event_id": event["event_id"],
                "classification": event["payload"].get("classification"),
                "classification_evidence": event["payload"].get("classification_evidence"),
            }
            for event in events
            if "classification" in event["payload"]
        ]
        # Job records carry the worker-returned classification/OOS verdicts for the
        # families that persist them only in result_json (GP, neuroevolution,
        # strategy composition, pareto). Including the job records (results plus
        # logs) is what makes this bundle complete enough to re-analyse offline.
        with self._connection() as connection:
            job_rows = connection.execute(
                "SELECT * FROM jobs WHERE experiment_id = ? ORDER BY created_at",
                (experiment_id,),
            ).fetchall()
            job_event_rows = connection.execute(
                """SELECT job_events.* FROM job_events
                   JOIN jobs ON jobs.job_id = job_events.job_id
                   WHERE jobs.experiment_id = ? ORDER BY job_events.event_id""",
                (experiment_id,),
            ).fetchall()
        events_by_job: dict[str, list[dict[str, Any]]] = {}
        for event in job_event_rows:
            events_by_job.setdefault(event["job_id"], []).append(
                {**dict(event), "payload": json.loads(event["payload_json"])}
            )
        jobs: list[dict[str, Any]] = []
        for row in job_rows:
            item = dict(row)
            item["parameters"] = json.loads(item.pop("parameters_json"))
            if item["result_json"] is not None:
                item["result"] = json.loads(item.pop("result_json"))
            else:
                item.pop("result_json")
                item["result"] = None
            item["events"] = events_by_job.get(item["job_id"], [])
            jobs.append(item)
        return {
            "experiment_id": experiment_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "experiment": experiment,
            "environment": environments[-1] if environments else None,
            "events": list(events),
            "candidates": list(candidates),
            "oos_acceptances": oos_acceptances,
            "classification_reports": classification_reports,
            "jobs": jobs,
            "candidate_count": len(candidates),
            "event_count": len(events),
            "job_count": len(jobs),
        }

    def evolution_snapshot(self, experiment_id: str) -> dict[str, Any]:
        """Aggregate population/generation monitoring state from stored rows (audit F-031)."""
        # Workers need not be alive: every generation statistic is derived from the
        # immutable candidate rows and lifecycle events the GP/neuro runners persist.
        self.get_experiment(experiment_id)
        candidates = self.candidates(experiment_id)
        per_generation: dict[int, dict[str, Any]] = {}
        mutation_count = 0
        crossover_count = 0
        for candidate in candidates:
            generation = int(candidate["generation"])
            bucket = per_generation.setdefault(generation, {
                "generation": generation,
                "population_size": 0,
                "fitnesses": [],
                "genome_keys": [],
            })
            bucket["population_size"] += 1
            metrics = candidate["metrics"]
            fitness = None
            if isinstance(metrics, dict) and isinstance(metrics.get("train_fitness"), (int, float)):
                fitness = float(metrics["train_fitness"])
            bucket["fitnesses"].append(fitness)
            parameters = candidate["parameters"]
            # Diversity compares stored genomes (expression trees or weight vectors)
            # as canonical JSON; identical stored genomes collapse to one distinct key.
            bucket["genome_keys"].append(json.dumps(
                parameters, sort_keys=True, separators=(",", ":"), allow_nan=False,
                default=str,
            ))
            lineage = candidate["lineage"]
            operator = lineage.get("operator") if isinstance(lineage, dict) else None
            operator_text = str(operator) if operator is not None else ""
            if "mutation" in operator_text:
                mutation_count += 1
            if "crossover" in operator_text:
                crossover_count += 1
        generations: list[dict[str, Any]] = []
        for bucket in sorted(per_generation.values(), key=lambda item: item["generation"]):
            fitnesses = [value for value in bucket["fitnesses"] if value is not None]
            distinct = set(bucket["genome_keys"])
            count = bucket["population_size"]
            generations.append({
                "generation": bucket["generation"],
                "population_size": count,
                "best_fitness": max(fitnesses) if fitnesses else None,
                "median_fitness": (
                    float(statistics.median(fitnesses)) if fitnesses else None
                ),
                "worst_fitness": min(fitnesses) if fitnesses else None,
                "diversity": len(distinct) / count,
                "evaluated_count": len(fitnesses),
                "failed_count": count - len(fitnesses),
            })
        events = self.events(experiment_id)
        latest_freeze: dict[str, Any] | None = None
        oos_events: list[dict[str, Any]] = []
        for event in events:
            if event["event_type"].endswith("_candidate_frozen"):
                latest_freeze = {
                    "event_type": event["event_type"],
                    "occurred_at": event["occurred_at"],
                    "payload": event["payload"],
                }
            elif event["event_type"].endswith("_oos_recorded"):
                oos_events.append({
                    "event_type": event["event_type"],
                    "occurred_at": event["occurred_at"],
                    "payload": event["payload"],
                })
        return {
            "experiment_id": experiment_id,
            "candidate_count": len(candidates),
            "generation_count": len(generations),
            "generations": generations,
            "mutation_count": mutation_count,
            "crossover_count": crossover_count,
            "latest_freeze_event": latest_freeze,
            "oos_events": oos_events,
            "source": "stored_candidates_and_events; workers need not be alive",
        }

    def job_resource_snapshots(self, job_id: str) -> tuple[dict[str, Any], ...]:
        """Return recorded resource snapshots for one job in append order (audit F-032)."""
        # Snapshots are plain job events, so this query works whether the worker
        # recorded them at start, at checkpoints or at job end.
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT event_id, job_id, event_type, occurred_at, payload_json
                   FROM job_events
                   WHERE job_id = ? AND event_type = 'resource_snapshot'
                   ORDER BY event_id""",
                (job_id,),
            ).fetchall()
        return tuple(
            {**dict(row), "payload": json.loads(row["payload_json"])}
            for row in rows
        )

    def list_job_results(
        self, experiment_id: str, *, limit: int = 100
    ) -> tuple[dict[str, Any], ...]:
        """Return one row per job for an experiment with its decoded result (F-030)."""
        # Job results carry classification/OOS verdicts for runner families that
        # persist them only in result_json; reading them stays market-scoped and
        # bounded like every other listing query.
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT job_id, experiment_id, runner_name, status,
                          created_at, started_at, completed_at, result_json
                   FROM jobs WHERE experiment_id = ?
                   ORDER BY created_at LIMIT ?""",
                (experiment_id, limit),
            ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            if item["result_json"] is not None:
                item["result"] = json.loads(item.pop("result_json"))
            else:
                item.pop("result_json")
                item["result"] = None
            output.append(item)
        return tuple(output)


    # ------------------------------------------------------------------
    # Worker leases and resumable checkpoints (audit F-026 / F-027).
    # Lease ownership is stored as nullable columns on the jobs row so a
    # claim/renew/expire decision is one atomic UPDATE under SQLite's write
    # lock, while every transition is also appended to job_events for audit.
    # Checkpoints are an append-only table: each row's integrity digest is
    # re-derived on load, so a truncated or tampered checkpoint is refused.
    # ------------------------------------------------------------------

    def acquire_job_lease(
        self, job_id: str, worker_id: str, *, ttl_seconds: int
    ) -> bool:
        """Atomically claim a claimable job for this worker; False when taken."""
        # A lease is claimable when the row is unleased or its expiry has passed.
        if not worker_id.strip() or ttl_seconds < 1:
            raise ValueError("worker_id must be non-empty and ttl_seconds positive")
        now = datetime.now(timezone.utc)
        expiry = (now + timedelta(seconds=ttl_seconds)).isoformat()
        token = uuid.uuid4().hex
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status, lease_owner, lease_expires_at FROM jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                raise KeyError(job_id)
            if row["status"] not in {"queued", "running", "failed"}:
                # failed/running jobs are interruptible and claimable; only
                # terminal succeeded/cancelled outcomes are never re-leased.
                return False
            current_expiry = row["lease_expires_at"]
            actively_leased = (
                row["lease_owner"] is not None
                and current_expiry is not None
                and datetime.fromisoformat(current_expiry) > now
            )
            if actively_leased:
                connection.execute(
                    """INSERT INTO job_events
                       (job_id, event_type, occurred_at, payload_json)
                       VALUES (?, 'lease_rejected', ?, ?)""",
                    (
                        job_id,
                        now.isoformat(),
                        json.dumps(
                            {
                                "requested_by": worker_id,
                                "lease_owner": row["lease_owner"],
                                "lease_expires_at": current_expiry,
                                "reason": "job is actively leased by another worker",
                            },
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    ),
                )
                return False
            updated = connection.execute(
                """UPDATE jobs
                   SET lease_owner = ?, lease_expires_at = ?, lease_token = ?
                   WHERE job_id = ? AND (
                       lease_owner IS NULL
                       OR lease_expires_at IS NULL
                       OR lease_expires_at <= ?
                   )""",
                (worker_id, expiry, token, job_id, now.isoformat()),
            )
            if updated.rowcount != 1:
                return False
            connection.execute(
                """INSERT INTO job_events
                   (job_id, event_type, occurred_at, payload_json)
                   VALUES (?, 'lease_acquired', ?, ?)""",
                (
                    job_id,
                    now.isoformat(),
                    json.dumps(
                        {
                            "worker_id": worker_id,
                            "lease_token": token,
                            "expires_at": expiry,
                            "ttl_seconds": ttl_seconds,
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                ),
            )
            return True

    def renew_job_lease(
        self, job_id: str, worker_id: str, *, ttl_seconds: int
    ) -> bool:
        """Heartbeat-renew a live lease held by this worker."""
        if not worker_id.strip() or ttl_seconds < 1:
            raise ValueError("worker_id must be non-empty and ttl_seconds positive")
        now = datetime.now(timezone.utc)
        expiry = (now + timedelta(seconds=ttl_seconds)).isoformat()
        with self._connection() as connection:
            updated = connection.execute(
                """UPDATE jobs
                   SET lease_expires_at = ?
                   WHERE job_id = ? AND lease_owner = ? AND lease_expires_at > ?""",
                (expiry, job_id, worker_id, now.isoformat()),
            )
            renewed = updated.rowcount == 1
            if renewed:
                connection.execute(
                    """INSERT INTO job_events
                       (job_id, event_type, occurred_at, payload_json)
                       VALUES (?, 'lease_renewed', ?, ?)""",
                    (
                        job_id,
                        now.isoformat(),
                        json.dumps(
                            {"worker_id": worker_id, "expires_at": expiry},
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    ),
                )
            return renewed

    def release_job_lease(self, job_id: str, worker_id: str) -> bool:
        """Release this worker's lease and record the transition."""
        now = datetime.now(timezone.utc)
        with self._connection() as connection:
            row = connection.execute(
                "SELECT lease_owner FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if row is None:
                raise KeyError(job_id)
            if row["lease_owner"] != worker_id:
                return False
            connection.execute(
                """UPDATE jobs
                   SET lease_owner = NULL, lease_expires_at = NULL, lease_token = NULL
                   WHERE job_id = ? AND lease_owner = ?""",
                (job_id, worker_id),
            )
            connection.execute(
                """INSERT INTO job_events
                   (job_id, event_type, occurred_at, payload_json)
                   VALUES (?, 'lease_released', ?, ?)""",
                (
                    job_id,
                    now.isoformat(),
                    json.dumps({"worker_id": worker_id}, sort_keys=True,
                               separators=(",", ":")),
                ),
            )
            return True

    def expire_stale_job_leases(self) -> int:
        """Expire every lapsed lease and mark each expired transition auditable."""
        now = datetime.now(timezone.utc)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """SELECT job_id, lease_owner FROM jobs
                   WHERE lease_owner IS NOT NULL AND lease_expires_at <= ?""",
                (now.isoformat(),),
            ).fetchall()
            for row in rows:
                connection.execute(
                    """UPDATE jobs
                       SET lease_owner = NULL, lease_expires_at = NULL, lease_token = NULL
                       WHERE job_id = ?""",
                    (row["job_id"],),
                )
                connection.execute(
                    """INSERT INTO job_events
                       (job_id, event_type, occurred_at, payload_json)
                       VALUES (?, 'lease_expired', ?, ?)""",
                    (
                        row["job_id"],
                        now.isoformat(),
                        json.dumps(
                            {
                                "worker_id": row["lease_owner"],
                                "expired_at": now.isoformat(),
                            },
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    ),
                )
            return len(rows)

    def job_lease(self, job_id: str) -> dict[str, Any] | None:
        """Return the live lease on a job, or None when unleased or expired."""
        with self._connection() as connection:
            row = connection.execute(
                """SELECT lease_owner, lease_expires_at, lease_token
                   FROM jobs WHERE job_id = ?""",
                (job_id,),
            ).fetchone()
            if row is None:
                raise KeyError(job_id)
        if row["lease_owner"] is None or row["lease_expires_at"] is None:
            return None
        if datetime.fromisoformat(row["lease_expires_at"]) <= datetime.now(timezone.utc):
            return None
        return {
            "job_id": job_id,
            "worker_id": row["lease_owner"],
            "expires_at": row["lease_expires_at"],
            "lease_token": row["lease_token"],
        }

    @staticmethod
    def _checkpoint_digest(
        *,
        job_id: str,
        created_at: str,
        progress: dict[str, Any],
        random_state: dict[str, Any] | None,
        candidates: list[dict[str, Any]],
        environment: dict[str, Any] | None,
    ) -> str:
        """Hash the checkpoint content so truncation or tampering is detectable."""
        payload = json.dumps(
            {
                "job_id": job_id,
                "created_at": created_at,
                "progress": progress,
                "random_state": random_state,
                "candidates": candidates,
                "environment": environment,
            },
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def append_job_checkpoint(
        self,
        job_id: str,
        *,
        progress: dict[str, Any] | None = None,
        random_state: dict[str, Any] | None = None,
        candidates_so_far: list[dict[str, Any]] | None = None,
        environment: dict[str, Any] | None = None,
    ) -> int:
        """Persist one verified resumable checkpoint for a job (audit F-026)."""
        # Checkpoints capture progress state, the candidate set so far, the RNG
        # state and the environment record; the integrity digest is re-derived
        # on load, so a resumed worker never trusts a truncated row.
        progress = dict(progress or {})
        candidates = list(candidates_so_far or [])
        for entry in candidates:
            if not isinstance(entry, dict) or not str(entry.get("candidate_digest", "")).strip():
                raise ValueError(
                    "checkpoint candidates_so_far entries require a candidate_digest"
                )
        if environment is not None and not isinstance(environment, dict):
            raise TypeError("checkpoint environment must be a record dictionary or None")
        now = datetime.now(timezone.utc).isoformat()
        digest = self._checkpoint_digest(
            job_id=job_id,
            created_at=now,
            progress=progress,
            random_state=random_state,
            candidates=candidates,
            environment=environment,
        )
        encoded = lambda value: json.dumps(  # noqa: E731 - local narrow helper
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        with self._connection() as connection:
            cursor = connection.execute(
                """INSERT INTO job_checkpoints
                   (job_id, created_at, progress_json, random_state_json,
                    candidates_json, environment_json, integrity_digest)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    job_id,
                    now,
                    encoded(progress),
                    None if random_state is None else encoded(random_state),
                    encoded(candidates),
                    None if environment is None else encoded(environment),
                    digest,
                ),
            )
            return int(cursor.lastrowid)

    def load_validated_checkpoint(self, job_id: str) -> dict[str, Any] | None:
        """Return the newest integrity-verified checkpoint, or None when absent."""
        with self._connection() as connection:
            row = connection.execute(
                """SELECT * FROM job_checkpoints WHERE job_id = ?
                   ORDER BY checkpoint_id DESC LIMIT 1""",
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        progress = json.loads(row["progress_json"])
        random_state = (
            None if row["random_state_json"] is None
            else json.loads(row["random_state_json"])
        )
        candidates = json.loads(row["candidates_json"])
        environment = (
            None if row["environment_json"] is None
            else json.loads(row["environment_json"])
        )
        expected = self._checkpoint_digest(
            job_id=row["job_id"],
            created_at=row["created_at"],
            progress=progress,
            random_state=random_state,
            candidates=candidates,
            environment=environment,
        )
        if expected != row["integrity_digest"]:
            # A truncated or tampered checkpoint is refused, never partially trusted.
            raise RuntimeError(
                f"checkpoint {row['checkpoint_id']} for job {job_id} failed its "
                "integrity digest; refusing to resume from unverified state"
            )
        return {
            "checkpoint_id": int(row["checkpoint_id"]),
            "job_id": row["job_id"],
            "created_at": row["created_at"],
            "progress": progress,
            "random_state": random_state,
            "candidates_so_far": candidates,
            "environment": environment,
            "integrity_digest": expected,
        }

    def reset_job_for_resume(self, job_id: str) -> None:
        """Move an interrupted/failed job back to queued for checkpointed resumption."""
        # A crashed worker leaves its job 'failed' or still marked 'running'
        # (its lease expired); both may re-enter the queue. A live lease is
        # refused so a single job never runs in two workers at once.
        with self._connection() as connection:
            row = connection.execute(
                "SELECT status FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if row is None:
                raise KeyError(job_id)
            if row["status"] not in {"failed", "running"}:
                raise ValueError(
                    f"only interrupted or failed jobs may be reset for resume; "
                    f"status is {row['status']!r}"
                )
            if row["status"] == "running":
                live_lease = connection.execute(
                    "SELECT lease_owner, lease_expires_at FROM jobs WHERE job_id = ?",
                    (job_id,),
                ).fetchone()
                still_leased = (
                    live_lease["lease_owner"] is not None
                    and live_lease["lease_expires_at"] is not None
                    and datetime.fromisoformat(live_lease["lease_expires_at"])
                    > datetime.now(timezone.utc)
                )
                if still_leased:
                    raise RuntimeError(
                        f"job {job_id} is actively leased by worker "
                        f"{live_lease['lease_owner']!r}; resume refused"
                    )
            connection.execute(
                """UPDATE jobs
                   SET status = 'queued', completed_at = NULL, error_message = NULL
                   WHERE job_id = ?""",
                (job_id,),
            )
