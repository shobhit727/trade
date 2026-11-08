"""Bounded, persistent execution of explicitly registered research runners."""

from __future__ import annotations

from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import StrEnum
from threading import Event, RLock
from typing import Any, Callable
from uuid import uuid4

from .storage import ExperimentStore


class JobStatus(StrEnum):
    """Persisted research job lifecycle states."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobCancelled(RuntimeError):
    """Raised by a cooperative runner after a cancellation request."""


@dataclass(slots=True)
class JobContext:
    """Per-job logging and cooperative cancellation channel."""

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


class ResearchJobManager:
    """Run allow-listed Python callables with fixed concurrency and durable job state."""

    def __init__(
        self,
        store: ExperimentStore,
        *,
        max_workers: int = 2,
        max_queued: int = 16,
    ) -> None:
        # Bound resource use even when a dashboard submits many jobs.
        if max_workers < 1 or max_queued < 0:
            raise ValueError("max_workers must be positive and max_queued non-negative")
        self.store = store
        self.max_workers = max_workers
        self.max_queued = max_queued
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="research-worker",
        )
        self._runners: dict[str, ResearchRunner] = {}
        self._contexts: dict[str, JobContext] = {}
        self._futures: dict[str, Future] = {}
        self._lock = RLock()
        self._closed = False

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
            duplicate_active = [
                item for item in active
                if item["experiment_id"] == experiment_id
                and item["runner_name"] == runner_name
            ]
            if duplicate_active:
                raise RuntimeError(
                    "an active job already exists for this experiment and runner"
                )
            if len(active) >= self.max_workers + self.max_queued:
                raise RuntimeError("research job queue is full")
            job_id = str(uuid4())
            self.store.create_job(
                job_id=job_id,
                experiment_id=experiment_id,
                runner_name=runner_name,
                parameters=payload,
            )
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
            result = runner(context, experiment, parameters)
            context.check_cancelled()
            if not isinstance(result, dict):
                raise TypeError("research runner must return a JSON-compatible object")
            self.store.update_job_status(job_id, JobStatus.SUCCEEDED.value, result=result)
            self.store.append_job_event(
                job_id,
                "job_succeeded",
                {"result_keys": sorted(str(key) for key in result)},
            )
        except JobCancelled as exc:
            # Cancellation is terminal and distinguishable from a worker failure.
            current = self.store.get_job(job_id)["status"]
            if current in {JobStatus.QUEUED.value, JobStatus.RUNNING.value}:
                self.store.update_job_status(
                    job_id,
                    JobStatus.CANCELLED.value,
                    error_message=str(exc)[:2000],
                )
            self.store.append_job_event(job_id, "job_cancelled", {"reason": str(exc)[:2000]})
        except Exception as exc:  # noqa: BLE001 - persist failure summaries without tracebacks.
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
