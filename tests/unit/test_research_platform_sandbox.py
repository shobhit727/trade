"""Adversarial tests for OS-boundary holdout isolation (audit F-002/F-003, CR-002).

Covers CR-002 items 3, 10, 11, 12, 13 and 14 at the unit level:

- normal workers cannot read protected holdout files (denial recorded);
- an explicit worker read attempt against a protected path fails;
- ``override=True`` produces a recorded, logged warning;
- a restarted worker meets the same denial;
- two concurrent invocations isolate independently;
- the unprivileged tier engages when ``euid != 0`` and permission bits are
  restored after the finally block;
- the unprivileged tier refuses to run as root without a drop account.

Root-user caveats: DAC never binds root, so read-denial assertions are skipped
when the suite runs as root (CI determinism; the privileged tier is exercised
there instead via its record trail). The graceful ``nobody``-missing skip is
applied to the root-tier identity test.
"""

from __future__ import annotations

import logging
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from research.platform import sandbox
from research.platform.sandbox import run_isolated

IS_ROOT = os.geteuid() == 0
pytestmark = pytest.mark.usefixtures("_isolate_sandbox_state")


@pytest.fixture
def _isolate_sandbox_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep module-level run records out of neighbouring tests."""
    monkeypatch.setattr(sandbox, "last_denials", [])
    monkeypatch.setattr(sandbox, "last_run", None)


def _python() -> str:
    return sys.executable or "python3"


@pytest.fixture
def holdout_layout(tmp_path: Path) -> dict[str, Path]:
    """A protected 0o600 holdout file and a non-holdout partition store."""
    protected = tmp_path / "holdout" / "final_holdout.csv"
    protected.parent.mkdir()
    protected.write_text("timestamp,close\n2099-01-01,secret\n")
    protected.chmod(0o600)
    data_root = tmp_path / "partitions" / "ds1"
    data_root.mkdir(parents=True)
    (data_root / "non_holdout.csv").write_text(
        "timestamp,close\n2024-01-01,public\n"
    )
    return {"protected": protected, "data_root": data_root, "tmp": tmp_path}


def worker_code(read_partition: bool, protected_path: Path | None) -> str:
    """Worker script: read the staged partition and/or the protected path."""
    lines = ["import os, sys"]
    if read_partition:
        lines.append(
            "data = open(os.environ['RESEARCH_SANDBOX_WORKDIR'] + '/non_holdout.csv').read()"
        )
        lines.append("print('PARTITION:' + ('public' if 'public' in data else 'MISSING'))")
    if protected_path is not None:
        target = str(protected_path)
        lines.append("outcome = 'UNSET'")
        lines.append("try:")
        lines.append(f"    open({target!r}, 'r')")
        lines.append("    outcome = 'LEAK'")
        lines.append("except (PermissionError, OSError):")
        lines.append("    outcome = 'DENIED'")
        lines.append("print('PROTECTED:' + outcome)")
    lines.append("sys.exit(0)")
    return "\n".join(lines)


def run_worker(
    layout: dict[str, Path],
    *,
    read_partition: bool,
    protected_read: bool,
    **kwargs: object,
) -> subprocess.CompletedProcess[str] | None:
    """Invoke :func:`run_isolated` against a worker built by :func:`worker_code`."""
    protected = (
        layout["protected"] if protected_read else None
    )
    code = worker_code(read_partition, protected)
    run_isolated(
        [_python(), "-c", code],
        [str(layout["protected"])] if protected_read else [],
        data_root=str(layout["data_root"]),
        **kwargs,  # type: ignore[arg-type]
    )
    return sandbox.last_run


class TestNormalWorkerReadsOnlyNonHoldout:
    """CR-002: the worker uses the safe copy; protected rows stay unreadable."""

    def test_worker_reads_staged_non_holdout_partition(
        self, holdout_layout: dict[str, Path]
    ) -> None:
        run = run_worker(holdout_layout, read_partition=True, protected_read=False)
        assert run is not None and run.exit_code == 0
        assert "PARTITION:public" in run.stdout

    @pytest.mark.skipif(
        IS_ROOT, reason="DAC does not bind root; denial semantics are POSIX-user tests"
    )
    def test_worker_cannot_read_protected_file(
        self, holdout_layout: dict[str, Path]
    ) -> None:
        run = run_worker(holdout_layout, read_partition=True, protected_read=True)
        assert run is not None and run.exit_code == 0
        assert "PROTECTED:DENIED" in run.stdout
        kinds = {record.kind for record in run.records}
        assert "protected_read_denied" in kinds

    @pytest.mark.skipif(
        not IS_ROOT,
        reason="privileged-tier record trail is only produced when running as root",
    )
    def test_root_tier_records_kernel_enforced_drop(
        self, holdout_layout: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            sandbox, "_resolve_drop_identity", lambda: (65534, 65534)
        )
        run = run_worker(holdout_layout, read_partition=False, protected_read=False)
        assert run is not None and run.exit_code == 0
        kinds = {record.kind for record in run.records}
        assert kinds == {"protected_read_denied"}
        assert any("setgroups" in record.detail for record in run.records)


class TestExplicitProtectedReadAttempt:
    """CR-002 items 10-11: denial is enforced and recorded."""

    @pytest.mark.skipif(
        IS_ROOT, reason="DAC does not bind root; denial semantics are POSIX-user tests"
    )
    def test_worker_read_attempt_denied_and_recorded(
        self, holdout_layout: dict[str, Path]
    ) -> None:
        run = run_worker(holdout_layout, read_partition=False, protected_read=True)
        assert run is not None and run.exit_code == 0
        assert "PROTECTED:DENIED" in run.stdout
        assert "PROTECTED:LEAK" not in run.stdout
        denials = [r for r in run.records if r.kind == "protected_read_denied"]
        assert denials, "worker's denied read attempt was not recorded"
        assert denials[0].path == str(holdout_layout["protected"])
        assert denials[0].worker_pid == run.worker_pid


class TestOverrideWarning:
    """``override=True`` must produce an explicit, recorded warning."""

    def test_override_records_warning(
        self,
        holdout_layout: dict[str, Path],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="research.platform.sandbox"):
            run = run_worker(
                holdout_layout, read_partition=False, protected_read=False, override=True
            )
        assert run is not None and run.exit_code == 0
        overrides = [r for r in run.records if r.kind == "override_requested"]
        assert len(overrides) == 1
        assert "best-effort" in overrides[0].detail
        assert any(
            record.levelno >= logging.WARNING
            and "override" in record.getMessage().lower()
            for record in caplog.records
        )

    def test_no_override_record_without_flag(
        self, holdout_layout: dict[str, Path]
    ) -> None:
        run = run_worker(holdout_layout, read_partition=False, protected_read=False)
        assert run is not None
        assert all(r.kind != "override_requested" for r in run.records)


class TestRestartSameDenial:
    """CR-002 item 12 (restart): a fresh worker meets the same denial."""

    @pytest.mark.skipif(
        IS_ROOT, reason="DAC does not bind root; denial semantics are POSIX-user tests"
    )
    def test_second_invocation_same_denial(
        self, holdout_layout: dict[str, Path]
    ) -> None:
        first = run_worker(holdout_layout, read_partition=False, protected_read=True)
        assert first is not None
        assert "PROTECTED:DENIED" in first.stdout
        second = run_worker(holdout_layout, read_partition=False, protected_read=True)
        assert second is not None
        assert "PROTECTED:DENIED" in second.stdout
        assert first.worker_pid != second.worker_pid
        # Denial trail is identical modulo the per-run worker PID.
        def trail(run: sandbox.RunResult) -> list[tuple[str, str, str]]:
            return [(r.kind, r.path, r.detail) for r in run.records]

        assert trail(first) == trail(second)

    def test_partition_readable_across_restarts(
        self, holdout_layout: dict[str, Path]
    ) -> None:
        for _ in range(2):
            run = run_worker(holdout_layout, read_partition=True, protected_read=False)
            assert run is not None and run.exit_code == 0
            assert "PARTITION:public" in run.stdout


class TestConcurrency:
    """CR-002 item 12: parallel invocations isolate independently.

    Each slot gets its OWN protected file and data root, so the two outer
    processes never share a revoke window (the in-process lock cannot
    serialise cross-process chmods). Each child records what its worker saw,
    and every slot is asserted to have observed a real denial.
    """

    def test_two_concurrent_invocations_isolate_independently(
        self, tmp_path: Path
    ) -> None:
        import json
        from concurrent.futures import ThreadPoolExecutor

        def build_slot(slot: str) -> dict[str, Path]:
            protected = tmp_path / f"holdout-{slot}" / "final_holdout.csv"
            protected.parent.mkdir(parents=True)
            protected.write_text(f"timestamp,close\n2099-01-01,secret-{slot}\n")
            protected.chmod(0o600)
            data_root = tmp_path / f"partitions-{slot}" / "ds1"
            data_root.mkdir(parents=True)
            (data_root / "non_holdout.csv").write_text(
                f"timestamp,close\n2024-01-01,public-{slot}\n"
            )
            return {"protected": protected, "data_root": data_root}

        slots = {slot: build_slot(slot) for slot in ("A", "B")}
        worker_payload = (
            "import os, sys\n"
            "try:\n"
            "    open(os.environ['PROTECTED'], 'r')\n"
            "    outcome = 'LEAK'\n"
            "except (PermissionError, OSError):\n"
            "    outcome = 'DENIED'\n"
            "print('PROTECTED:' + outcome)\n"
        )
        # The outer child runs run_isolated and records its own run's evidence.
        invocation = (
            "import json, os, sys\n"
            "sys.path.insert(0, {src!r})\n"
            "from research.platform import sandbox\n"
            "from research.platform.sandbox import run_isolated\n"
            "worker = [{py!r}, '-c', os.environ['WORKER_PAYLOAD']]\n"
            "exit_code = run_isolated(\n"
            "    worker,\n"
            "    [os.environ['PROTECTED']],\n"
            "    data_root=os.environ['DATA_ROOT'],\n"
            ")\n"
            "payload = {{\n"
            "    'slot': os.environ['SLOT'],\n"
            "    'exit_code': exit_code,\n"
            "    'worker_stdout': sandbox.last_run.stdout if sandbox.last_run else '',\n"
            "    'denial_kinds': sorted(\n"
            "        r.kind for r in sandbox.last_denials\n"
            "        if r.kind == 'protected_read_denied'\n"
            "    ),\n"
            "    'worker_pid': sandbox.last_run.worker_pid if sandbox.last_run else None,\n"
            "}}\n"
            "with open(os.environ['RESULTS'], 'w') as handle:\n"
            "    json.dump(payload, handle)\n"
        ).format(src=str(Path(__file__).resolve().parents[2] / "src"), py=_python())
        results = {
            slot: tmp_path / f"results-{slot}.json" for slot in slots
        }
        env = dict(os.environ)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {
                slot: pool.submit(
                    subprocess.run,
                    [_python(), "-c", invocation],
                    capture_output=True,
                    text=True,
                    env={
                        **env,
                        "SLOT": slot,
                        "PROTECTED": str(layout["protected"]),
                        "DATA_ROOT": str(layout["data_root"]),
                        "WORKER_PAYLOAD": worker_payload,
                        "RESULTS": str(results[slot]),
                    },
                    cwd=os.getcwd(),
                )
                for slot, layout in slots.items()
            }
            outcomes = {slot: future.result() for slot, future in futures.items()}
        for slot, outcome in outcomes.items():
            assert outcome.returncode == 0, f"slot {slot}: {outcome.stderr}"

        # F-003: each slot must have observed a genuine denial, not a leak.
        payloads = {
            slot: json.loads(results[slot].read_text()) for slot in slots
        }
        for slot, payload in payloads.items():
            assert payload["exit_code"] == 0, payload
            assert "PROTECTED:DENIED" in payload["worker_stdout"], payload
            assert payload["denial_kinds"] == ["protected_read_denied"], payload
            assert payload["worker_pid"] is not None, payload
        # The two workers were distinct processes, each in its own window.
        pids = {payload["worker_pid"] for payload in payloads.values()}
        assert len(pids) == 2

        # CR-002: every protected file restored to its original 0o600.
        for layout in slots.values():
            assert stat.S_IMODE(layout["protected"].stat().st_mode) == 0o600
class TestUnprivilegedTierSemantics:
    """F-002: tier selection and permission restoration after the finally."""

    def test_unprivileged_tier_engages_when_euid_nonzero(
        self,
        holdout_layout: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        engaged: dict[str, bool] = {}

        def fake_unprivileged(*args: object, **kwargs: object) -> tuple[int, int, str, str, list]:
            engaged["called"] = True
            return (0, 1, "", "", [])

        monkeypatch.setattr(
            sandbox.os, "geteuid", lambda: 1000, raising=True
        )
        monkeypatch.setattr(sandbox, "_run_unprivileged", fake_unprivileged)
        monkeypatch.setattr(
            sandbox,
            "_run_privileged",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("privileged tier must not run when euid != 0")
            ),
        )
        exit_code = run_isolated(
            [_python(), "-c", "pass"],
            [str(holdout_layout["protected"])],
            data_root=str(holdout_layout["data_root"]),
        )
        assert exit_code == 0
        assert engaged.get("called") is True

    @pytest.mark.skipif(
        not IS_ROOT,
        reason="root without a drop account is only reachable when euid == 0",
    )
    def test_root_without_nobody_falls_back(
        self,
        holdout_layout: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import pwd as pwd_module

        monkeypatch.setattr(
            pwd_module, "getpwnam", _raise_key_error
        )
        monkeypatch.setattr(
            sandbox.os, "geteuid", lambda: 0, raising=True
        )
        engaged: dict[str, bool] = {}

        def fake_unprivileged(*args: object, **kwargs: object) -> tuple[int, int, str, str, list]:
            engaged["called"] = True
            return (0, 1, "", "", [])

        monkeypatch.setattr(sandbox, "_run_unprivileged", fake_unprivileged)
        exit_code = run_isolated(
            [_python(), "-c", "pass"],
            [str(holdout_layout["protected"])],
            data_root=str(holdout_layout["data_root"]),
        )
        assert exit_code == 0
        assert engaged.get("called") is True
        kinds = {record.kind for record in sandbox.last_denials}
        assert "tier_fallback" in kinds

    @pytest.mark.skipif(
        not IS_ROOT,
        reason="root without a drop account is only reachable when euid == 0",
    )
    def test_root_without_nobody_skips_gracefully(
        self, holdout_layout: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CI determinism: a root host lacking 'nobody' must degrade, not crash."""
        try:
            import pwd as pwd_module

            pwd_module.getpwnam("nobody")
        except KeyError:
            pytest.skip("no 'nobody' account; uid-drop semantics untestable here")
        monkeypatch.setattr(pwd_module, "getpwnam", _raise_key_error)
        exit_code = run_isolated(
            [_python(), "-c", "pass"],
            [str(holdout_layout["protected"])],
            data_root=str(holdout_layout["data_root"]),
        )
        assert exit_code == 0

    def test_mode_bits_restored_after_finally(
        self, holdout_layout: dict[str, Path], tmp_path: Path
    ) -> None:
        """Protected bits survive a run, including a worker that fails."""
        protected = holdout_layout["protected"]
        before = stat.S_IMODE(protected.stat().st_mode)
        run_isolated(
            [_python(), "-c", "raise SystemExit(3)"],
            [str(protected)],
            data_root=str(holdout_layout["data_root"]),
        )
        assert stat.S_IMODE(protected.stat().st_mode) == before

        tree = tmp_path / "tree"
        (tree / "nested").mkdir(parents=True)
        leaf = tree / "nested" / "leaf.csv"
        leaf.write_text("x")
        tree.chmod(0o750)
        (tree / "nested").chmod(0o750)
        leaf.chmod(0o640)
        snapshot = (
            stat.S_IMODE(tree.stat().st_mode),
            stat.S_IMODE((tree / "nested").stat().st_mode),
            stat.S_IMODE(leaf.stat().st_mode),
        )
        run_isolated(
            [_python(), "-c", "pass"],
            [str(tree)],
            data_root=str(holdout_layout["data_root"]),
        )
        after = (
            stat.S_IMODE(tree.stat().st_mode),
            stat.S_IMODE((tree / "nested").stat().st_mode),
            stat.S_IMODE(leaf.stat().st_mode),
        )
        assert after == snapshot

    def test_no_stale_staging_directories(
        self, holdout_layout: dict[str, Path], tmp_path: Path
    ) -> None:
        run_isolated(
            [_python(), "-c", "pass"],
            [str(holdout_layout["protected"])],
            data_root=str(holdout_layout["data_root"]),
        )
        leftovers = list(Path(tempfile_root()).glob("research-sandbox-*"))
        assert leftovers == []

    def test_worker_cannot_persist_artefacts_via_staging(
        self, holdout_layout: dict[str, Path]
    ) -> None:
        """CR-002 item 13: staged artefacts are discarded with the run."""
        exfiltration = (
            "import os\n"
            "open(os.environ['RESEARCH_SANDBOX_WORKDIR'] + '/stolen.csv', 'w').write('rows')\n"
        )
        run = sandbox_run(exfiltration, holdout_layout)
        assert run is not None and run.exit_code == 0
        staged_dir = holdout_layout["data_root"].parent / "nonexistent"
        assert not staged_dir.exists()
        assert not list(holdout_layout["data_root"].rglob("stolen.csv"))


def tempfile_root() -> str:
    import tempfile

    return tempfile.gettempdir()


def sandbox_run(
    code: str, layout: dict[str, Path], **kwargs: object
) -> sandbox.RunResult | None:
    run_isolated(
        [_python(), "-c", code],
        [str(layout["protected"])],
        data_root=str(layout["data_root"]),
        **kwargs,  # type: ignore[arg-type]
    )
    return sandbox.last_run


def _raise_key_error(name: str) -> None:
    raise KeyError(f"getpwnam(): name not found: {name}")


class TestGuardrails:
    """The boundary refuses layouts it cannot honour."""

    def test_protected_path_inside_data_root_rejected(
        self, holdout_layout: dict[str, Path], tmp_path: Path
    ) -> None:
        nested = holdout_layout["data_root"] / "inner.csv"
        nested.write_text("x")
        with pytest.raises(ValueError):
            run_isolated(
                [_python(), "-c", "pass"],
                [str(nested)],
                data_root=str(holdout_layout["data_root"]),
            )

    def test_missing_protected_path_rejected(
        self, holdout_layout: dict[str, Path], tmp_path: Path
    ) -> None:
        with pytest.raises(FileNotFoundError):
            run_isolated(
                [_python(), "-c", "pass"],
                [str(tmp_path / "does-not-exist.csv")],
                data_root=str(holdout_layout["data_root"]),
            )
