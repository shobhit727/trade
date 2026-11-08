"""SQLite-backed append-only experiment and evolutionary-lineage registry."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

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
                CREATE INDEX IF NOT EXISTS idx_candidates_experiment
                    ON candidates(experiment_id, generation);
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
