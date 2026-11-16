"""Resumable checkpoints and worker-lease tests (audit F-026 / F-027, section 7.18)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from research.platform.domain import AlgorithmFamily, DataResolution, Market, ResearchTrack
from research.platform.experiments import ExperimentSpec
from research.platform.jobs import ResearchJobManager
from research.platform.reproducibility import capture_environment_record
from research.platform.storage import ExperimentStore

REPO_ROOT = "/home/ph03n1x/trade/.worktrees/feature"
UTC = timezone.utc


def _spec() -> ExperimentSpec:
    return ExperimentSpec(
        experiment_id="resume-test",
        market=Market.NSE,
        track=ResearchTrack.NSE_INDIVIDUAL,
        algorithm_family=AlgorithmFamily.EXISTING_STRATEGY,
        resolution=DataResolution.ONE_DAY,
        dataset_ids=("test-dataset",),
        random_seed=7,
        git_commit="0123456789abcdef0123456789abcdef01234567",
        code_version="resume-test",
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


def _store(path: Path) -> ExperimentStore:
    store = ExperimentStore(path)
    store.create_experiment(_spec())
    return store


def _checkpoint_payload(seed: int = 7, generations: int = 3) -> dict:
    """A complete checkpoint body: progress, RNG state, candidate set, environment."""
    rng = np.random.default_rng(seed)
    return {
        "progress": {"generation": generations, "evaluations": generations * 10},
        "random_state": rng.bit_generator.state,
        "candidates_so_far": [
            {"candidate_digest": f"{index:064x}", "generation": index}
            for index in range(generations)
        ],
        "environment": capture_environment_record(
            seed=seed,
            compute_backend=_spec().compute_backend,
            repo_root=REPO_ROOT,
        ),
    }


def test_checkpoint_roundtrip_restores_identical_candidate_set(tmp_path) -> None:
    # Persist -> new store instance -> resume: the candidate set must be identical.
    path = tmp_path / "resume.sqlite3"
    store = _store(path)
    store.create_job(
        job_id="roundtrip", experiment_id="resume-test",
        runner_name="worker", parameters={},
    )
    payload = _checkpoint_payload(generations=5)
    # The reference stream resumes from the checkpointed state, then advances;
    # the restored stream must produce the same subsequent values.
    rng = np.random.default_rng()
    rng.bit_generator.state = payload["random_state"]
    store.append_job_checkpoint(
        "roundtrip",
        progress=payload["progress"],
        random_state=payload["random_state"],
        candidates_so_far=payload["candidates_so_far"],
        environment=payload["environment"],
    )
    # Reopen the store BEFORE advancing: a resumed worker restarts from the
    # checkpointed state, then advances identically to the original stream.
    reopened = ExperimentStore(path)  # a fresh store instance, as after a crash
    checkpoint = reopened.load_validated_checkpoint("roundtrip")
    assert checkpoint is not None
    assert checkpoint["progress"] == {"generation": 5, "evaluations": 50}
    assert [c["candidate_digest"] for c in checkpoint["candidates_so_far"]] == [
        f"{index:064x}" for index in range(5)
    ]
    restored_rng = np.random.default_rng()
    restored_rng.bit_generator.state = checkpoint["random_state"]
    # Both streams advance identically from the checkpointed state: the RNG
    # state resumed exactly (identical draws for every subsequent step).
    expected = [int(rng.integers(0, 1000)) for _ in range(8)]
    resumed = [int(restored_rng.integers(0, 1000)) for _ in range(8)]
    assert expected == resumed


def test_environment_divergent_checkpoint_is_refused(tmp_path) -> None:
    # A checkpoint captured under a different seed/environment must not resume.
    path = tmp_path / "divergent.sqlite3"
    store = _store(path)
    store.create_job(
        job_id="divergent", experiment_id="resume-test",
        runner_name="worker", parameters={},
    )
    foreign = _checkpoint_payload(seed=7)
    foreign["environment"]["random_seed"] = 8  # a divergent machine/seed record
    store.append_job_checkpoint(
        "divergent",
        progress=foreign["progress"],
        random_state=foreign["random_state"],
        candidates_so_far=foreign["candidates_so_far"],
        environment=foreign["environment"],
    )
    # A crashed worker leaves the job failed before the resume is attempted.
    store.update_job_status("divergent", "running")
    store.update_job_status("divergent", "failed", error_message="crash")
    manager = ResearchJobManager(store, leases_enabled=False)
    manager.register_runner("worker", lambda context, experiment, parameters: {})
    with pytest.raises(RuntimeError, match="diverges from this worker"):
        manager.resume("divergent")
    # Refusal leaves no half-claimed state: the record is still failed.
    assert store.get_job("divergent")["status"] == "failed"
    manager.shutdown(wait=True)


def test_checkpoint_without_environment_record_is_refused(tmp_path) -> None:
    # An environment-free checkpoint cannot prove provenance and is refused.
    path = tmp_path / "noenv.sqlite3"
    store = _store(path)
    store.create_job(
        job_id="noenv", experiment_id="resume-test",
        runner_name="worker", parameters={},
    )
    store.append_job_checkpoint(
        "noenv",
        progress={"generation": 1},
        random_state=None,
        candidates_so_far=[],
        environment=None,
    )
    store.update_job_status("noenv", "running")
    store.update_job_status("noenv", "failed", error_message="crash")
    manager = ResearchJobManager(store, leases_enabled=False)
    manager.register_runner("worker", lambda context, experiment, parameters: {})
    with pytest.raises(RuntimeError, match="no complete environment record"):
        manager.resume("noenv")
    manager.shutdown(wait=True)


def test_tampered_recorded_seed_is_refused_by_spec_anchor(tmp_path) -> None:
    # The recorded seed is NOT trusted: a checkpoint claiming a different seed
    # diverges from the spec-anchored re-derivation and must be refused.
    path = tmp_path / "seed.sqlite3"
    store = _store(path)
    store.create_job(
        job_id="seedshift", experiment_id="resume-test",
        runner_name="worker", parameters={},
    )
    payload = _checkpoint_payload(seed=8)  # captured under a foreign seed
    store.append_job_checkpoint(
        "seedshift",
        progress=payload["progress"],
        random_state=payload["random_state"],
        candidates_so_far=payload["candidates_so_far"],
        environment=payload["environment"],
    )
    store.update_job_status("seedshift", "running")
    store.update_job_status("seedshift", "failed", error_message="crash")
    manager = ResearchJobManager(store, leases_enabled=False)
    manager.register_runner("worker", lambda context, experiment, parameters: {})
    with pytest.raises(RuntimeError, match="diverges from this worker"):
        manager.resume("seedshift")
    assert store.get_job("seedshift")["status"] == "failed"
    manager.shutdown(wait=True)


def test_tampered_checkpoint_integrity_digest_is_refused(tmp_path) -> None:
    # The integrity digest is re-derived on load; a mutated row is never trusted.
    path = tmp_path / "tampered.sqlite3"
    store = _store(path)
    store.create_job(
        job_id="tampered", experiment_id="resume-test",
        runner_name="worker", parameters={},
    )
    payload = _checkpoint_payload()
    store.append_job_checkpoint(
        "tampered",
        progress=payload["progress"],
        random_state=payload["random_state"],
        candidates_so_far=payload["candidates_so_far"],
        environment=payload["environment"],
    )
    # Mutate a byte-level copy (append-only triggers block in-place UPDATEs).
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TRIGGER immutable_job_checkpoints_update")
        connection.execute(
            "UPDATE job_checkpoints SET progress_json = ?",
            (json.dumps({"generation": 99, "evaluations": 990}),),
        )
    with pytest.raises(RuntimeError, match="integrity digest"):
        ExperimentStore(path).load_validated_checkpoint("tampered")


def _progress_runner(store: ExperimentStore, crash_after: int):
    """A runner that checkpoints and persists candidates, then simulates a crash."""

    def runner(context, experiment, parameters):
        resumed = parameters.get("resumed_state") or {}
        already = list(resumed.get("candidates_so_far", []))
        start = len(already)
        context.log(f"resuming at generation {start}" if start else "fresh run")
        candidates = list(already)
        for generation in range(start, 6):
            candidates.append({
                "candidate_digest": f"{generation:064x}",
                "generation": generation,
            })
            # Idempotent persistence keyed on (experiment_id, candidate_digest).
            if not store.has_candidate("resume-test", f"{generation:064x}"):
                store.append_candidate(
                    candidate_id=f"cand-{generation:064x}",
                    experiment_id="resume-test",
                    candidate_digest=f"{generation:064x}",
                    family="genetic_programming",
                    generation=generation,
                    parameters={"generation": generation},
                    metrics={"train_fitness": 0.1 * generation},
                    lineage={"operator": "seed"},
                )
            rng = np.random.default_rng(7 + generation)
            context.checkpoint(
                progress={"generation": generation + 1},
                random_state=rng.bit_generator.state,
                candidates_so_far=candidates,
                environment=capture_environment_record(
                    seed=7,
                    compute_backend=_spec().compute_backend,
                    repo_root=REPO_ROOT,
                ),
            )
            if generation == crash_after:
                # Simulate worker death between checkpoints: the process dies
                # before the next checkpoint, leaving the last one durable.
                raise RuntimeError("worker crash")
        return {"generations": 6, "candidates": len(candidates)}

    return runner


def test_crash_mid_evaluation_resumes_without_duplicate_candidates(tmp_path) -> None:
    # Crash after generation 2 -> resume -> identical candidate digests, no dupes.
    path = tmp_path / "crash.sqlite3"
    store = _store(path)
    manager = ResearchJobManager(store, leases_enabled=False)
    manager.register_runner("crashy", _progress_runner(store, crash_after=2))
    job_id = manager.submit("resume-test", "crashy")
    job = manager.wait(job_id, timeout=10)
    assert job["status"] == "failed"
    assert "worker crash" in job["error_message"]
    persisted = {row["candidate_digest"] for row in store.candidates("resume-test")}
    assert persisted == {f"{index:064x}" for index in range(3)}

    # A fresh manager (as after process restart) resumes the crashed job.
    resumed_manager = ResearchJobManager(ExperimentStore(path), leases_enabled=False)
    resumed_manager.register_runner("crashy", _progress_runner(store, crash_after=99))
    resumed_manager.resume(job_id)
    job = resumed_manager.wait(job_id, timeout=10)
    assert job["status"] == "succeeded", job.get("error_message")
    rows = store.candidates("resume-test")
    digests = [row["candidate_digest"] for row in rows]
    assert len(digests) == 6
    assert len(set(digests)) == 6  # no duplicate candidate persistence
    assert digests == sorted(digests)
    events = [e["event_type"] for e in store.get_job(job_id)["events"]]
    assert "job_resumed" in events
    assert "job_resume_requested" in events
    resumed_manager.shutdown(wait=True)


def test_startup_recovery_then_resume_completes_with_checkpoint(tmp_path) -> None:
    # api startup force-fails live jobs (recover_interrupted_jobs); a job with a
    # verified checkpoint must still resume cleanly afterwards (7.18 rows 3+8).
    path = tmp_path / "recovery.sqlite3"
    store = _store(path)
    store.create_job(
        job_id="recovered", experiment_id="resume-test",
        runner_name="worker", parameters={},
    )
    store.update_job_status("recovered", "running")
    payload = _checkpoint_payload()
    store.append_job_checkpoint(
        "recovered",
        progress=payload["progress"],
        random_state=payload["random_state"],
        candidates_so_far=payload["candidates_so_far"],
        environment=payload["environment"],
    )
    assert store.recover_interrupted_jobs() == 1
    assert store.get_job("recovered")["status"] == "failed"

    def runner(context, experiment, parameters):
        resumed = parameters.get("resumed_state") or {}
        return {"resumed_candidates": len(resumed.get("candidates_so_far", []))}

    manager = ResearchJobManager(store, leases_enabled=False)
    manager.register_runner("worker", runner)
    manager.resume("recovered")
    job = manager.wait("recovered", timeout=10)
    assert job["status"] == "succeeded", job.get("error_message")
    assert job["result"]["resumed_candidates"] == 3
    manager.shutdown(wait=True)


def test_lease_transitions_persist_as_queryable_events(tmp_path) -> None:
    # acquire/renew/expire/reject/release all appear in the append-only history.
    path = tmp_path / "lease.sqlite3"
    store = _store(path)
    store.create_job(
        job_id="leased", experiment_id="resume-test",
        runner_name="worker", parameters={},
    )
    assert store.acquire_job_lease("leased", "worker-a", ttl_seconds=300)
    assert not store.acquire_job_lease("leased", "worker-b", ttl_seconds=300)
    assert store.renew_job_lease("leased", "worker-a", ttl_seconds=300)
    with store._connection() as connection:
        connection.execute(
            "UPDATE jobs SET lease_expires_at = ? WHERE job_id = 'leased'",
            ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(),),
        )
    assert store.job_lease("leased") is None
    assert store.expire_stale_job_leases() == 1
    assert store.acquire_job_lease("leased", "worker-b", ttl_seconds=300)
    assert store.release_job_lease("leased", "worker-b")
    events = [e["event_type"] for e in store.get_job("leased")["events"]]
    assert events == [
        "lease_acquired",
        "lease_rejected",
        "lease_renewed",
        "lease_expired",
        "lease_acquired",
        "lease_released",
    ]
    payloads = {e["event_type"]: e["payload"] for e in store.get_job("leased")["events"]}
    assert payloads["lease_rejected"]["requested_by"] == "worker-b"
    assert payloads["lease_rejected"]["lease_owner"] == "worker-a"
    assert payloads["lease_expired"]["worker_id"] == "worker-a"


def test_active_lease_rejects_second_worker(tmp_path) -> None:
    # A second worker cannot start an actively-leased job: explicit rejection.
    path = tmp_path / "reject.sqlite3"
    store = _store(path)
    store.create_job(
        job_id="contested", experiment_id="resume-test",
        runner_name="worker", parameters={},
    )
    assert store.acquire_job_lease("contested", "worker-a", ttl_seconds=300)
    assert store.job_lease("contested")["worker_id"] == "worker-a"
    assert not store.acquire_job_lease("contested", "worker-b", ttl_seconds=300)
    rejections = [
        e for e in store.get_job("contested")["events"]
        if e["event_type"] == "lease_rejected"
    ]
    assert len(rejections) == 1
    assert rejections[0]["payload"]["requested_by"] == "worker-b"
    # Still held by worker-a afterwards.
    assert store.job_lease("contested")["worker_id"] == "worker-a"


def test_expired_lease_reclaimed_by_second_worker(tmp_path) -> None:
    # After the TTL lapses, another worker can claim and run the job.
    path = tmp_path / "reclaim.sqlite3"
    store = _store(path)
    manager_a = ResearchJobManager(
        store, leases_enabled=True, lease_ttl_seconds=1, worker_id="worker-a"
    )
    manager_a.register_runner(
        "worker", lambda context, experiment, parameters: {"done": True}
    )
    job_id = manager_a.submit("resume-test", "worker")
    assert manager_a.wait(job_id, timeout=10)["status"] == "succeeded"
    # Completed release means no lease remains; a fresh claim is an acquire.
    assert manager_a.store.job_lease(job_id) is None

    # Expiry path: lease a long-lived record, force its TTL to lapse, re-claim.
    store.create_job(
        job_id="reclaimed", experiment_id="resume-test",
        runner_name="worker", parameters={},
    )
    assert store.acquire_job_lease("reclaimed", "worker-a", ttl_seconds=3600)
    with store._connection() as connection:
        connection.execute(
            "UPDATE jobs SET lease_expires_at = ? WHERE job_id = 'reclaimed'",
            ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(),),
        )
    manager_b = ResearchJobManager(store, leases_enabled=True, worker_id="worker-b")
    manager_b.register_runner(
        "worker", lambda context, experiment, parameters: {"done": True}
    )
    assert store.acquire_job_lease("reclaimed", "worker-b", ttl_seconds=300)
    assert store.job_lease("reclaimed")["worker_id"] == "worker-b"
    manager_a.shutdown(wait=True)
    manager_b.shutdown(wait=True)


def test_leased_execution_rejects_foreign_result_writes(tmp_path) -> None:
    # A worker that lost its lease must not persist results (F-027 guard).
    path = tmp_path / "foreign.sqlite3"
    store = _store(path)
    manager = ResearchJobManager(
        store, leases_enabled=True, lease_ttl_seconds=1, worker_id="worker-a"
    )

    def runner(context, experiment, parameters):
        # The heartbeat keeps the lease alive; simulate a stolen lease instead.
        with store._connection() as connection:
            connection.execute(
                "UPDATE jobs SET lease_owner = 'worker-b' WHERE job_id = ?",
                (context.job_id,),
            )
        return {"stolen": True}

    manager.register_runner("worker", runner)
    job_id = manager.submit("resume-test", "worker")
    job = manager.wait(job_id, timeout=10)
    assert job["status"] in {"running", "queued", "failed"}
    # The result must NOT have been persisted by the leaseless worker.
    assert job["result"] is None or "stolen" not in json.dumps(job["result"])
    events = [e["event_type"] for e in store.get_job(job_id)["events"]]
    assert "lease_rejected" in events
    manager.shutdown(wait=True, cancel_pending=True)


def test_single_process_default_requires_no_lease(tmp_path) -> None:
    # Default mode: jobs run without any lease machinery (audit wording holds).
    path = tmp_path / "default.sqlite3"
    store = _store(path)
    manager = ResearchJobManager(store)
    manager.register_runner(
        "worker", lambda context, experiment, parameters: {"done": True}
    )
    assert manager.leases_enabled is False
    job_id = manager.submit("resume-test", "worker")
    job = manager.wait(job_id, timeout=10)
    assert job["status"] == "succeeded"
    lease_events = [
        e for e in store.get_job(job_id)["events"]
        if e["event_type"].startswith("lease_")
    ]
    assert lease_events == []
    manager.shutdown(wait=True)


def test_resume_requires_checkpoint_and_terminal_state(tmp_path) -> None:
    # A succeeded job or a checkpoint-less job cannot be resumed.
    path = tmp_path / "guards.sqlite3"
    store = _store(path)
    manager = ResearchJobManager(store, leases_enabled=False)
    manager.register_runner(
        "worker", lambda context, experiment, parameters: {"done": True}
    )
    job_id = manager.submit("resume-test", "worker")
    assert manager.wait(job_id, timeout=10)["status"] == "succeeded"
    with pytest.raises(ValueError, match="not resumable"):
        manager.resume(job_id)
    manager.shutdown(wait=True)

    store.create_job(
        job_id="nocheckpoint", experiment_id="resume-test",
        runner_name="worker", parameters={},
    )
    store.update_job_status("nocheckpoint", "running")
    store.update_job_status("nocheckpoint", "failed", error_message="crash")
    manager2 = ResearchJobManager(store, leases_enabled=False)
    manager2.register_runner("worker", lambda c, e, p: {})
    with pytest.raises(ValueError, match="no checkpoint"):
        manager2.resume("nocheckpoint")
    manager2.shutdown(wait=True)
