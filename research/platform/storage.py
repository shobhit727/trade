"""SQLite-backed append-only experiment and evolutionary-lineage registry."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .data_catalog import DatasetManifest
from .experiments import ExperimentSpec


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
                    error_message TEXT
                );
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
                """
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
        result = dict(row)
        result["manifest"] = json.loads(result.pop("manifest_json"))
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
        output = []
        for row in rows:
            # Surface metadata already registered with the immutable dataset manifest.
            item = dict(row)
            manifest = json.loads(item.pop("manifest_json"))
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
