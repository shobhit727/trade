"""Bounded, persistent execution of explicitly registered research runners.

Jobs persist every lifecycle transition, a resumable checkpoint stream
(audit F-026 / section 7.18) and, when ``RESEARCH_WORKER_LEASE=1`` is set,
an explicit worker-lease trail (audit F-027). Single-process execution
remains the default and requires no lease.
"""

from __future__ import annotations

import os
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import StrEnum
from threading import Event, RLock, Thread
from typing import Any, Callable
from uuid import uuid4

from .reproducibility import (
    ReproducibilityMismatch,
    reproduce_check,
)
from .storage import ExperimentStore

#: Environment variable that opts a deployment into leased distributed workers.
WORKER_LEASE_ENV = "RESEARCH_WORKER_LEASE"
#: Lease time-to-live used when ``RESEARCH_WORKER_LEASE_TTL`` is unset.
DEFAULT_LEASE_TTL_SECONDS = 300


def lease_mode_enabled() -> bool:
    """Return whether distributed worker leasing is explicitly enabled."""
    # Distribution is opt-in: the default single-process manager needs no lease.
    return os.getenv(WORKER_LEASE_ENV, "0").strip().lower() == "1"


class JobStatus(StrEnum):
    """Persisted research job lifecycle states."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobCancelled(RuntimeError):
    """Raised by a cooperative runner after a cancellation request."""


class LeaseRejected(RuntimeError):
    """Raised when a worker may not execute a job leased to another worker."""


@dataclass(slots=True)
class JobContext:
    """Per-job logging, cooperative cancellation and resumable checkpoints."""

    job_id: str
    store: ExperimentStore
    cancel_event: Event = field(default_factory=Event)

    @property
    def cancellation_requested(self) -> bool:
        # Expose cancellation without giving runners access to manager internals.
        return self.cancel_event.is_set()

    def check_cancelled(self) -> None:
        """Raise JobCancelled at safe cancellation points in a runner."""
        if self.cancel_event.is_set():
            raise JobCancelled(f"job {self.job_id} cancellation requested")

    def checkpoint(
        self,
        progress: dict[str, Any] | None = None,
        *,
        random_state: dict[str, Any] | None = None,
        candidates_so_far: list[dict[str, Any]] | None = None,
        environment: dict[str, Any] | None = None,
    ) -> int:
        """Persist a verified resumable checkpoint for this job (audit F-026).

        ``random_state`` must be a JSON-serialisable NumPy bit-generator state
        (``generator.bit_generator.state``). Each ``candidates_so_far`` entry
        carries the immutable ``candidate_digest`` that makes candidate
        persistence idempotent across a crash and resume. ``environment``
        should be a full ``capture_environment_record`` payload so a resuming
        worker can refuse a checkpoint from a divergent machine.
        """
        return self.store.append_job_checkpoint(
            self.job_id,
            progress=dict(progress or {}),
            random_state=random_state,
            candidates_so_far=list(candidates_so_far or []),
            environment=environment,
        )

    def restore_checkpoint(self) -> dict[str, Any] | None:
        """Return the newest integrity-verified checkpoint for this job, or None."""
        return self.store.load_validated_checkpoint(self.job_id)

    def validation_lifecycle(self, experiment_id: str):
        """Restore or create this job's persistent candidate/OOS/holdout lifecycle."""
        # Job identity scopes durable transitions, while a separate job can be an audited rerun.
        from .validation import ValidationLifecycle

        return ValidationLifecycle(
            store=self.store,
            experiment_id=experiment_id,
            lifecycle_id=self.job_id,
        )

    def log(self, message: str, *, level: str = "info") -> None:
        """Append a structured progress message to persistent job history."""
        # Bound message length and restrict levels to protect the event store.
        if level not in {"debug", "info", "warning", "error"}:
            raise ValueError("job log level is invalid")
        self.store.append_job_event(
            self.job_id,
            "log",
            {"level": level, "message": str(message)[:2000]},
        )


ResearchRunner = Callable[
    [JobContext, dict[str, Any], dict[str, Any]],
    dict[str, Any],
]


def _validated_environment(
    checkpoint: dict[str, Any], *, seed: int, compute_backend: str
) -> None:
    """Reject a checkpoint captured in a divergent environment (reuses F-023 semantics).

    Seed and backend come from the immutable experiment SPEC (the requested
    configuration), mirroring ``ExistingStrategyJobRunner``'s F-023 idiom: a
    tampered recorded seed then fails the comparison through the
    ``random_seed`` field itself, and re-derivation uses the recorded request
    rather than a re-resolved backend probe.
    """
    environment = checkpoint.get("environment")
    if not isinstance(environment, dict):
        raise RuntimeError(
            "checkpoint carries no complete environment record; refusing to resume"
        )
    try:
        reproduce_check(environment, seed=seed, compute_backend=compute_backend)
    except ReproducibilityMismatch as exc:
        raise RuntimeError(
            f"checkpoint environment diverges from this worker: {exc}"
        ) from exc


class ResearchJobManager:
    """Run allow-listed Python callables with fixed concurrency and durable job state."""

    def __init__(
        self,
        store: ExperimentStore,
        *,
        max_workers: int = 2,
        max_queued: int = 16,
        worker_id: str | None = None,
        leases_enabled: bool | None = None,
        lease_ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
    ) -> None:
        # Bound resource use even when a dashboard submits many jobs.
        if max_workers < 1 or max_queued < 0:
            raise ValueError("max_workers must be positive and max_queued non-negative")
        if lease_ttl_seconds < 1:
            raise ValueError("lease_ttl_seconds must be positive")
        self.store = store
        self.max_workers = max_workers
        self.max_queued = max_queued
        self._worker_id = worker_id or f"worker-{os.getpid()}-{uuid4().hex[:8]}"
        # Leases are opt-in: the default single-process manager needs none.
        self._leases_enabled = (
            lease_mode_enabled() if leases_enabled is None else bool(leases_enabled)
        )
        self._lease_ttl = int(lease_ttl_seconds)
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="research-worker",
        )
        self._runners: dict[str, ResearchRunner] = {}
        self._contexts: dict[str, JobContext] = {}
        self._futures: dict[str, Future] = {}
        self._heartbeat_stops: dict[str, Event] = {}
        self._lock = RLock()
        self._closed = False

    @property
    def worker_id(self) -> str:
        """Return this manager's persisted lease identity."""
        return self._worker_id

    @property
    def leases_enabled(self) -> bool:
        """Return whether jobs are executed under a controlled worker lease."""
        return self._leases_enabled

    def register_runner(self, name: str, runner: ResearchRunner) -> None:
        """Register a named trusted runner; clients can only choose registered names."""
        # Runner identifiers are data labels, never module paths or source code.
        if not name or not name.replace("_", "").isalnum():
            raise ValueError("runner name must be a non-empty alphanumeric/underscore identifier")
        if not callable(runner):
            raise TypeError("runner must be callable")
        with self._lock:
            if self._closed:
                raise RuntimeError("job manager is closed")
            if name in self._runners:
                raise ValueError(f"runner already registered: {name}")
            self._runners[name] = runner

    def runner_names(self) -> tuple[str, ...]:
        """Return the explicit allow-list for the experiment API."""
        with self._lock:
            return tuple(sorted(self._runners))

    def submit(
        self,
        experiment_id: str,
        runner_name: str,
        parameters: dict[str, Any] | None = None,
    ) -> str:
        """Create a queued job and submit only an allow-listed runner."""
        # Resolve the experiment and runner before allocating worker resources.
        experiment = self.store.get_experiment(experiment_id)
        payload = dict(parameters or {})
        with self._lock:
            if self._closed:
                raise RuntimeError("job manager is closed")
            runner = self._runners.get(runner_name)
            if runner is None:
                raise ValueError(f"unknown research runner: {runner_name}")
            active = [
                item for item in self.store.list_jobs(limit=1000)
                if item["status"] in {JobStatus.QUEUED.value, JobStatus.RUNNING.value}
            ]
            if len(active) >= self.max_workers + self.max_queued:
                raise RuntimeError("research job queue is full")
            duplicate_active = [
                item for item in active
                if item["experiment_id"] == experiment_id
                and item["runner_name"] == runner_name
            ]
            if duplicate_active:
                raise RuntimeError(
                    "an active job already exists for this experiment and runner"
                )
            job_id = str(uuid4())
            self.store.create_job(
                job_id=job_id,
                experiment_id=experiment_id,
                runner_name=runner_name,
                parameters=payload,
            )
            if self._leases_enabled:
                if not self.store.acquire_job_lease(
                    job_id, self._worker_id, ttl_seconds=self._lease_ttl
                ):
                    # Guard against races; a fresh row cannot be leased elsewhere.
                    self.store.update_job_status(
                        job_id,
                        JobStatus.FAILED.value,
                        error_message="could not acquire worker lease",
                    )
                    raise RuntimeError("could not acquire worker lease for the new job")
            context = JobContext(job_id=job_id, store=self.store)
            self._contexts[job_id] = context
            self.store.append_job_event(
                job_id,
                "job_queued",
                {"runner_name": runner_name, "experiment_id": experiment_id},
            )
            future = self._executor.submit(
                self._execute,
                job_id,
                runner,
                experiment,
                payload,
                context,
            )
            self._futures[job_id] = future
        return job_id

    def resume(self, job_id: str) -> str:
        """Re-arm an interrupted job from its newest verified checkpoint (audit F-026).

        The checkpoint's candidate digests and integrity digests are re-derived
        before the job is re-queued; its environment record is re-validated
        against this worker just before the runner runs.
        """
        with self._lock:
            if self._closed:
                raise RuntimeError("job manager is closed")
            job = self.store.get_job(job_id)
            if job["status"] not in {JobStatus.RUNNING.value, JobStatus.FAILED.value}:
                raise ValueError(
                    f"job {job_id} is not resumable from status {job['status']!r}"
                )
            runner = self._runners.get(job["runner_name"])
            if runner is None:
                raise ValueError(f"unknown research runner: {job['runner_name']}")
            checkpoint = self.store.load_validated_checkpoint(job_id)
            if checkpoint is None:
                raise ValueError(f"job {job_id} has no checkpoint to resume from")
            # Refuse a divergent checkpoint BEFORE re-queuing the job so a
            # rejected resume leaves no half-claimed state behind (F-026).
            experiment = self.store.get_experiment(job["experiment_id"])
            spec = experiment["spec"]
            _validated_environment(
                checkpoint,
                seed=int(spec["random_seed"]),
                compute_backend=str(spec.get("compute_backend", "numpy")),
            )
            # Reset to queued BEFORE claiming: a failed/running record is only
            # claimable once it is back in the queued interruptible set.
            self.store.reset_job_for_resume(job_id)
            if self._leases_enabled and not self.store.acquire_job_lease(
                job_id, self._worker_id, ttl_seconds=self._lease_ttl
            ):
                raise LeaseRejected(
                    f"job {job_id} is actively leased by another worker"
                )
            parameters = dict(job["parameters"])
            context = JobContext(job_id=job_id, store=self.store)
            self._contexts[job_id] = context
            self.store.append_job_event(
                job_id,
                "job_resume_requested",
                {
                    "checkpoint_id": checkpoint["checkpoint_id"],
                    "worker_id": self._worker_id,
                },
            )
            future = self._executor.submit(
                self._execute,
                job_id,
                runner,
                experiment,
                parameters,
                context,
            )
            self._futures[job_id] = future
        return job_id

    def _start_heartbeat(self, job_id: str) -> None:
        """Renew this worker's lease in the background for the job's lifetime."""
        if not self._leases_enabled:
            return
        stop = Event()
        self._heartbeat_stops[job_id] = stop

        def beat() -> None:
            # Renew well inside the TTL so a paused worker does not lose the job.
            interval = max(self._lease_ttl / 3.0, 0.05)
            while not stop.wait(interval):
                if not self.store.renew_job_lease(
                    job_id, self._worker_id, ttl_seconds=self._lease_ttl
                ):
                    self.store.append_job_event(
                        job_id,
                        "lease_lost",
                        {"worker_id": self._worker_id},
                    )
                    return

        Thread(target=beat, name=f"lease-heartbeat-{job_id[:8]}", daemon=True).start()

    def _stop_heartbeat(self, job_id: str) -> None:
        stop = self._heartbeat_stops.pop(job_id, None)
        if stop is not None:
            stop.set()

    def _release_lease(self, job_id: str) -> None:
        if self._leases_enabled:
            self.store.release_job_lease(job_id, self._worker_id)

    def _execute(
        self,
        job_id: str,
        runner: ResearchRunner,
        experiment: dict[str, Any],
        parameters: dict[str, Any],
        context: JobContext,
    ) -> None:
        # Persist state transitions before and after executing trusted runner code.
        try:
            context.check_cancelled()
            self.store.update_job_status(job_id, JobStatus.RUNNING.value)
            self.store.append_job_event(job_id, "job_started", {})
            self._start_heartbeat(job_id)
            checkpoint = self.store.load_validated_checkpoint(job_id)
            if checkpoint is not None:
                # Resume is refused unless the checkpoint's environment record
                # matches this worker's re-derived environment (F-023/F-026);
                # seed and backend are anchored to the immutable spec.
                _validated_environment(
                    checkpoint,
                    seed=int(experiment["spec"]["random_seed"]),
                    compute_backend=str(
                        experiment["spec"].get("compute_backend", "numpy")
                    ),
                )
                parameters = {**parameters, "resumed_state": checkpoint}
                self.store.append_job_event(
                    job_id,
                    "job_resumed",
                    {
                        "checkpoint_id": checkpoint["checkpoint_id"],
                        "candidate_count": len(checkpoint["candidates_so_far"]),
                    },
                )
            result = runner(context, experiment, parameters)
            context.check_cancelled()
            if not isinstance(result, dict):
                raise TypeError("research runner must return a JSON-compatible object")
            if self._leases_enabled:
                lease = self.store.job_lease(job_id)
                if lease is None or lease["worker_id"] != self._worker_id:
                    # Another worker took over; this attempt must not write results.
                    raise LeaseRejected(
                        f"worker lost the lease for job {job_id}; refusing to persist results"
                    )
            self.store.update_job_status(job_id, JobStatus.SUCCEEDED.value, result=result)
            self.store.append_job_event(
                job_id,
                "job_succeeded",
                {"result_keys": sorted(str(key) for key in result)},
            )
            self._release_lease(job_id)
        except JobCancelled as exc:
            # Cancellation is terminal and distinguishable from a worker failure.
            self._release_lease(job_id)
            current = self.store.get_job(job_id)["status"]
            if current in {JobStatus.QUEUED.value, JobStatus.RUNNING.value}:
                self.store.update_job_status(
                    job_id,
                    JobStatus.CANCELLED.value,
                    error_message=str(exc)[:2000],
                )
            self.store.append_job_event(job_id, "job_cancelled", {"reason": str(exc)[:2000]})
        except LeaseRejected as exc:
            # Another worker owns the job; do not touch its persisted status.
            self.store.append_job_event(
                job_id,
                "lease_rejected",
                {"worker_id": self._worker_id, "reason": str(exc)[:2000]},
            )
        except Exception as exc:  # noqa: BLE001 - persist failure summaries without tracebacks.
            self._release_lease(job_id)
            current = self.store.get_job(job_id)["status"]
            if current in {JobStatus.QUEUED.value, JobStatus.RUNNING.value}:
                self.store.update_job_status(
                    job_id,
                    JobStatus.FAILED.value,
                    error_message=f"{type(exc).__name__}: {exc}"[:2000],
                )
            self.store.append_job_event(
                job_id,
                "job_failed",
                {"error_type": type(exc).__name__, "message": str(exc)[:2000]},
            )
        finally:
            self._stop_heartbeat(job_id)

    def cancel(self, job_id: str) -> bool:
        """Request cancellation; running runners must poll JobContext.check_cancelled()."""
        job = self.store.get_job(job_id)
        if job["status"] not in {JobStatus.QUEUED.value, JobStatus.RUNNING.value}:
            return False
        with self._lock:
            context = self._contexts.get(job_id)
            future = self._futures.get(job_id)
            if context is None:
                return False
            context.cancel_event.set()
            cancelled_before_start = future.cancel() if future is not None else False
            if cancelled_before_start and job["status"] == JobStatus.QUEUED.value:
                self._release_lease(job_id)
                self.store.update_job_status(
                    job_id,
                    JobStatus.CANCELLED.value,
                    error_message="cancelled before worker start",
                )
                self.store.append_job_event(job_id, "job_cancelled", {
                    "reason": "cancelled before worker start"
                })
            else:
                self.store.append_job_event(job_id, "job_cancel_requested", {})
        return True

    def wait(self, job_id: str, timeout: float | None = None) -> dict[str, Any]:
        """Wait for a local worker and return its persisted status snapshot."""
        future = self._futures.get(job_id)
        if future is not None:
            try:
                future.result(timeout=timeout)
            except CancelledError:
                # A Future cancelled before start still has a durable cancelled DB record.
                pass
        return self.store.get_job(job_id)

    def get(self, job_id: str) -> dict[str, Any]:
        """Return a job status and its append-only event history."""
        return self.store.get_job(job_id)

    def list(self, experiment_id: str | None = None, limit: int = 100) -> tuple[dict[str, Any], ...]:
        """List persisted job summaries."""
        return self.store.list_jobs(experiment_id=experiment_id, limit=limit)

    def shutdown(self, *, wait: bool = True, cancel_pending: bool = False) -> None:
        """Stop accepting work and optionally cancel jobs that have not started."""
        with self._lock:
            self._closed = True
            if cancel_pending:
                for job in self.store.list_jobs(limit=1000):
                    if job["status"] == JobStatus.QUEUED.value:
                        self.cancel(job["job_id"])
            self._executor.shutdown(wait=wait, cancel_futures=cancel_pending)
        # Terminal or abandoned jobs must not retain this worker's lease.
        for job in self.store.list_jobs(limit=1000):
            lease = self.store.job_lease(job["job_id"])
            if lease is not None and lease["worker_id"] == self._worker_id:
                self.store.release_job_lease(job["job_id"], self._worker_id)
