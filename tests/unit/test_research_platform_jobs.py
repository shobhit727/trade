"""Tests for bounded, persistent research job execution."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Event

import pytest

from research.platform.domain import AlgorithmFamily, DataResolution, Market, ResearchTrack
from research.platform.experiments import ExperimentSpec
from research.platform.jobs import ResearchJobManager
from research.platform.storage import ExperimentStore


UTC = timezone.utc


def _spec() -> ExperimentSpec:
    # Metadata-only test experiment; no market data or credentials are required.
    return ExperimentSpec(
        experiment_id="job-manager-test",
        market=Market.NSE,
        track=ResearchTrack.NSE_INDIVIDUAL,
        algorithm_family=AlgorithmFamily.EXISTING_STRATEGY,
        resolution=DataResolution.ONE_DAY,
        dataset_ids=("test-dataset",),
        random_seed=7,
        git_commit="0123456789abcdef0123456789abcdef01234567",
        code_version="job-test",
        training_start=datetime(2010, 1, 1, tzinfo=UTC),
        training_end=datetime(2014, 1, 1, tzinfo=UTC),
        validation_start=datetime(2014, 1, 1, tzinfo=UTC),
        validation_end=datetime(2016, 1, 1, tzinfo=UTC),
        oos_start=datetime(2026, 10, 2, tzinfo=UTC),
        oos_end=datetime(2026, 10, 16, tzinfo=UTC),
        final_holdout_start=datetime(2026, 10, 16, tzinfo=UTC),
        final_holdout_end=datetime(2026, 11, 8, tzinfo=UTC),
        cost_model_id="test-cost-v1",
        execution_model_id="next-open-participation-impact-v1",
        objectives=("net_return",),
        parameters={"strategy_name": "metadata-only"},
        created_at=datetime(2026, 11, 8, tzinfo=UTC),
    )


def _manager(path, *, max_workers: int = 2, max_queued: int = 4):
    # Each test uses a dedicated experiment database.
    store = ExperimentStore(path)
    store.create_experiment(_spec())
    manager = ResearchJobManager(store, max_workers=max_workers, max_queued=max_queued)
    return store, manager


def test_job_manager_persists_success_result_and_progress_events(tmp_path) -> None:
    # A registered runner executes and produces a durable result record.
    store, manager = _manager(tmp_path / "jobs.sqlite3")

    def runner(context, experiment, parameters):
        # Runners can record progress and inspect immutable experiment metadata.
        context.log("starting calculation")
        context.check_cancelled()
        return {"experiment_id": experiment["experiment_id"], "answer": parameters["value"] * 2}

    manager.register_runner("simple_test", runner)
    job_id = manager.submit("job-manager-test", "simple_test", {"value": 21})
    job = manager.wait(job_id, timeout=5)
    assert job["status"] == "succeeded"
    assert job["result"]["answer"] == 42
    assert job["runner_name"] == "simple_test"
    assert any(event["event_type"] == "log" for event in job["events"])
    assert store.list_jobs(experiment_id="job-manager-test")[0]["job_id"] == job_id
    manager.shutdown()


def test_job_manager_persists_runner_failure_without_traceback(tmp_path) -> None:
    # Exceptions become bounded error summaries and a failed state.
    _, manager = _manager(tmp_path / "jobs.sqlite3")

    def runner(context, experiment, parameters):
        # A deterministic error verifies failure persistence.
        raise RuntimeError("deterministic runner failure")

    manager.register_runner("failing_test", runner)
    job_id = manager.submit("job-manager-test", "failing_test")
    job = manager.wait(job_id, timeout=5)
    assert job["status"] == "failed"
    assert "deterministic runner failure" in job["error_message"]
    assert any(event["event_type"] == "job_failed" for event in job["events"])
    manager.shutdown()


def test_job_manager_supports_cooperative_cancellation(tmp_path) -> None:
    # Running workers can be cancelled at safe polling points.
    _, manager = _manager(tmp_path / "jobs.sqlite3", max_workers=1)
    started = Event()

    def runner(context, experiment, parameters):
        # The runner controls where it is safe to stop.
        started.set()
        while True:
            context.check_cancelled()

    manager.register_runner("cancellable_test", runner)
    job_id = manager.submit("job-manager-test", "cancellable_test")
    assert started.wait(timeout=5)
    assert manager.cancel(job_id) is True
    job = manager.wait(job_id, timeout=5)
    assert job["status"] == "cancelled"
    assert any(event["event_type"] == "job_cancel_requested" for event in job["events"])
    manager.shutdown()


def test_job_manager_enforces_worker_queue_capacity(tmp_path) -> None:
    # Active plus queued jobs cannot exceed the configured capacity.
    _, manager = _manager(tmp_path / "jobs.sqlite3", max_workers=1, max_queued=0)
    started = Event()

    def runner(context, experiment, parameters):
        # Occupy the only worker until the job is cancelled.
        started.set()
        while True:
            context.check_cancelled()

    manager.register_runner("blocking_test", runner)
    first = manager.submit("job-manager-test", "blocking_test")
    assert started.wait(timeout=5)
    with pytest.raises(RuntimeError, match="queue is full"):
        manager.submit("job-manager-test", "blocking_test")
    assert manager.cancel(first)
    assert manager.wait(first, timeout=5)["status"] == "cancelled"
    manager.shutdown()


def test_job_manager_rejects_unknown_runner_names(tmp_path) -> None:
    # API callers cannot supply arbitrary Python callbacks or shell commands.
    _, manager = _manager(tmp_path / "jobs.sqlite3")
    with pytest.raises(ValueError, match="unknown research runner"):
        manager.submit("job-manager-test", "execute_shell_command")
    manager.shutdown()



def test_store_marks_queued_and_running_jobs_interrupted_after_restart(tmp_path) -> None:
    # ThreadPoolExecutor state is process-local; persisted active jobs must not look live.
    store, manager = _manager(tmp_path / "restart.sqlite3", max_workers=1)
    manager.register_runner("never_submitted", lambda context, experiment, parameters: {"ok": True})
    queued_id = "queued-before-restart"
    running_id = "running-before-restart"
    store.create_job(
        job_id=queued_id,
        experiment_id="job-manager-test",
        runner_name="never_submitted",
        parameters={},
    )
    store.create_job(
        job_id=running_id,
        experiment_id="job-manager-test",
        runner_name="never_submitted",
        parameters={},
    )
    store.update_job_status(running_id, "running")
    manager.shutdown(wait=True)

    recovered = store.recover_interrupted_jobs()
    assert recovered == 2
    assert store.get_job(queued_id)["status"] == "failed"
    assert store.get_job(running_id)["status"] == "failed"
    assert store.get_job(queued_id)["error_message"].startswith("worker process restarted")
    assert any(
        event["event_type"] == "job_interrupted_on_restart"
        for event in store.get_job(running_id)["events"]
    )
    # Recovery is idempotent; terminal jobs are not rewritten.
    assert store.recover_interrupted_jobs() == 0
