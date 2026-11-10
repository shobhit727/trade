"""OS-boundary holdout isolation for research workers (audit F-002/F-003, CR-002).

CR-002 requires that normal research workers have no file permission for
protected final-holdout data and that every access attempt is denied and
recorded. :func:`run_isolated` is the single entry point providing that
boundary at the OS level on a single research host.

Two tiers:

(a) Privileged tier -- when the process runs as root and an unprivileged
    account (``nobody``) exists, protected files are locked down to ``0o600``
    and protected directory trees to ``0o700`` (owner-only), and the worker is
    launched through ``preexec_fn`` which calls ``os.setgroups([])`` followed
    by ``os.setgid``/``os.setuid`` into the unprivileged account. The kernel
    then enforces the boundary for the worker.

(b) Unprivileged tier -- no privileged drop is possible (the common case on a
    single-user workstation). The non-holdout partition under ``data_root`` is
    copied into a fresh private temporary directory, the worker runs against
    that copy only, and for the worker's duration the protected sources have
    ALL permission bits revoked (files and directories to ``0o000``). On a
    single-user host the worker would otherwise run as the file owner, and
    revoking only group/other bits would deny it nothing; owner-only
    revocation is the minimum that satisfies CR-002 item 3 ("give normal
    workers no file permission for protected data") in this tier. Original
    modes are restored in a ``finally`` block, deepest entries first during
    lockdown and shallowest first during restore, so revocation never strands
    a nested entry behind an untraversable parent.

In both tiers the worker's only staged data is a private copy of the
non-holdout partition, exported as ``RESEARCH_SANDBOX_WORKDIR``. Worker
arteffacts are discarded with the staging directory when the run ends
(CR-002 item 13: a worker cannot copy protected rows into persistent
artefacts through this boundary).

``override=True`` never bypasses the boundary; it appends an explicit warning
record (emitted on the ``research.platform.sandbox`` logger and retained with
the run records) so a conscious relaxation is auditable.

Every protected-path access check performed for a run is recorded as a
:class:`DenialRecord`. The most recent run's records are available via
:data:`last_denials`, and its captured worker output via :data:`last_run`.

Threat model and limits: this is a best-effort OS boundary for single-user
research hosts. It is NOT a security product: it cannot constrain a worker
that runs as root (DAC does not bind root), it does not defend against kernel
or interpreter exploits, and a multi-tenant deployment still needs a
dedicated holdout service with a narrow input interface (CR-002 items 1-2).
"""

from __future__ import annotations

import contextlib
import logging
import os
import pwd
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

__all__ = ["DenialRecord", "RunResult", "run_isolated", "last_denials", "last_run"]

_LOGGER = logging.getLogger(__name__)

_DROP_USER = "nobody"

# Serialises the permission-revocation window across concurrent invocations so
# mode snapshots of the same protected path never interleave. Reentrant so a
# worker that itself calls run_isolated on the same thread cannot deadlock.
_ISOLATION_LOCK = threading.RLock()


@dataclass(frozen=True)
class DenialRecord:
    """One recorded access check or boundary event.

    ``kind`` is one of ``override_requested``, ``tier_fallback``,
    ``protected_read_denied`` or ``boundary_not_enforced``.
    """

    kind: str
    path: str
    worker_pid: int
    detail: str

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "path": self.path,
            "worker_pid": self.worker_pid,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class RunResult:
    """Outcome of one :func:`run_isolated` invocation."""

    exit_code: int
    worker_pid: int
    stdout: str
    stderr: str
    records: tuple[DenialRecord, ...]


# Records and captured output of the most recent :func:`run_isolated` call.
last_denials: list[DenialRecord] = []
last_run: RunResult | None = None


def _resolve_drop_identity() -> tuple[int, int] | None:
    """Return ``(uid, gid)`` of the unprivileged drop account, or ``None``."""
    try:
        entry = pwd.getpwnam(_DROP_USER)
    except KeyError:
        return None
    return entry.pw_uid, entry.pw_gid


def _tree_entries(path: Path) -> list[Path]:
    """Return ``path`` plus, for directories, every descendant."""
    if path.is_dir():
        return [path, *sorted(path.rglob("*"))]
    return [path]


def _depth(path: Path) -> int:
    return len(path.parts)


def _revoke_bits(
    entries: list[Path], target_bits: int, snapshots: dict[Path, int]
) -> None:
    """Revoke permission bits, snapshotting each original into ``snapshots``.

    Entries are processed deepest-first so a revoked parent never blocks
    reaching its not-yet-revoked children. Every entry is snapshotted into
    ``snapshots`` immediately before its own chmod, so an exception part-way
    through the tree never leaves an already-revoked entry out of the
    caller's finally-restore.
    """
    for entry in sorted(entries, key=_depth, reverse=True):
        current = entry.stat().st_mode & 0o777
        snapshots[entry] = current
        entry.chmod(current & target_bits)


def _restore_bits(snapshots: dict[Path, int]) -> None:
    """Restore snapshotted modes, shallowest-first.

    Restoring a parent directory before its children re-enables traversal, so
    nested entries never end up unreachable for their own restore.
    """
    for entry in sorted(snapshots, key=_depth):
        with contextlib.suppress(FileNotFoundError, PermissionError, OSError):
            entry.chmod(snapshots[entry])


def _guard_layout(protected: list[Path], data_root: Path, workdir: Path) -> None:
    """Refuse layouts the isolation tiers cannot honour."""
    for path in protected:
        if not path.exists():
            raise FileNotFoundError(f"protected path does not exist: {path}")
        if path == workdir or path in workdir.parents:
            raise ValueError(
                f"protected path contains the sandbox staging area: {path}"
            )
        if path == data_root or path in data_root.parents or data_root in path.parents:
            raise ValueError(
                f"protected path overlaps the non-holdout staging root: {path}"
            )


def _probe_denials(protected: list[Path], worker_pid: int) -> list[DenialRecord]:
    """Attempt one read per protected path and record the outcome.

    Probes run in the (unprivileged) parent while the protected bits are
    revoked, mirroring what the same-identity worker experiences.
    """
    records: list[DenialRecord] = []
    for path in protected:
        try:
            with open(path, "rb"):
                pass
        except (PermissionError, OSError):
            records.append(
                DenialRecord(
                    kind="protected_read_denied",
                    path=str(path),
                    worker_pid=worker_pid,
                    detail="open() denied while protected permission bits revoked",
                )
            )
            _LOGGER.info("recorded denial for protected path %s", path)
        else:
            records.append(
                DenialRecord(
                    kind="boundary_not_enforced",
                    path=str(path),
                    worker_pid=worker_pid,
                    detail=(
                        "probe read succeeded during sandbox window; the running "
                        "identity is not constrained by DAC (root?) - boundary "
                        "NOT enforced for this run"
                    ),
                )
            )
            _LOGGER.warning(
                "sandbox could not revoke access to %s; boundary not enforced", path
            )
    return records


def _run_privileged(
    cmd: list[str],
    protected: list[Path],
    workdir: Path,
    staged: Path,
    uid: int,
    gid: int,
) -> tuple[int, int, str, str, list[DenialRecord]]:
    """Tier (a): lock down to owner-only, then drop the worker to ``uid``/``gid``."""
    records: list[DenialRecord] = []
    snapshots: dict[Path, int] = {}
    # The staging area must accept the unprivileged worker's cwd and artefacts,
    # and the staged non-holdout copy must be readable by it regardless of the
    # caller's umask.
    os.chmod(workdir, 0o777)
    for entry in _tree_entries(staged):
        entry.chmod(0o755 if entry.is_dir() else 0o644)
    try:
        for path in protected:
            # Owner-only bits: files 0o600, directories 0o700 (owner is root).
            bits = 0o700 if path.is_dir() else 0o600
            _revoke_bits(_tree_entries(path), bits, snapshots)

        def _drop_privileges() -> None:  # pragma: no cover - runs in the child
            os.setgroups([])
            os.setgid(gid)
            os.setuid(uid)

        environment = dict(os.environ)
        environment["RESEARCH_SANDBOX_WORKDIR"] = str(staged)
        process = subprocess.Popen(
            cmd,
            cwd=str(workdir),
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=_drop_privileges,
        )
        records.append(
            DenialRecord(
                kind="protected_read_denied",
                path=", ".join(str(p) for p in protected) or "*",
                worker_pid=process.pid,
                detail=(
                    "root tier: protected bits reduced to owner-only and worker "
                    f"dropped to uid={uid}/gid={gid} via setgroups([])+setgid+setuid"
                ),
            )
        )
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            tail = (stderr or "").strip().splitlines()
            _LOGGER.warning(
                "isolated worker exited %s%s",
                process.returncode,
                f"; stderr: {tail[-1]}" if tail else "",
            )
        return process.returncode, process.pid, stdout, stderr, records
    finally:
        _restore_bits(snapshots)


def _run_unprivileged(
    cmd: list[str],
    protected: list[Path],
    workdir: Path,
    staged: Path,
) -> tuple[int, int, str, str, list[DenialRecord]]:
    """Tier (b): run against the staged copy with protected bits fully revoked."""
    records: list[DenialRecord] = []
    snapshots: dict[Path, int] = {}
    try:
        for path in protected:
            # Full owner-bit revocation: on a single-user host the worker runs
            # as the file owner, so only removing owner bits denies it (CR-002
            # item 3). Originals are restored in the finally below.
            _revoke_bits(_tree_entries(path), 0o000, snapshots)
        environment = dict(os.environ)
        environment["RESEARCH_SANDBOX_WORKDIR"] = str(staged)
        process = subprocess.Popen(
            cmd,
            cwd=str(workdir),
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        # Probes run while the worker is confined by the revoked bits.
        records.extend(_probe_denials(protected, process.pid))
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            tail = (stderr or "").strip().splitlines()
            _LOGGER.warning(
                "isolated worker exited %s%s",
                process.returncode,
                f"; stderr: {tail[-1]}" if tail else "",
            )
        return process.returncode, process.pid, stdout, stderr, records
    finally:
        _restore_bits(snapshots)


def run_isolated(
    cmd: list[str],
    protected_paths: list[str],
    *,
    data_root: str,
    override: bool = False,
) -> int:
    """Run ``cmd`` isolated from protected holdout data; return its exit code.

    See the module docstring for the two tiers and their limits. ``data_root``
    is the non-holdout partition store the worker may read; it is staged as a
    private copy and exported to the worker as ``RESEARCH_SANDBOX_WORKDIR``.
    ``protected_paths`` are files or directory trees the worker must not read;
    every access check against them is recorded. ``override=True`` appends an
    explicit override warning record. The records of the most recent run are
    also available as :data:`last_denials` and its captured worker output as
    :data:`last_run`.
    """
    global last_denials, last_run
    last_denials = []
    last_run = None

    protected = [Path(p).resolve() for p in protected_paths]
    data_root_path = Path(data_root).resolve()

    records: list[DenialRecord] = []
    if override:
        override_record = DenialRecord(
            kind="override_requested",
            path="*",
            worker_pid=os.getpid(),
            detail=(
                "explicit override requested: caller acknowledged the OS boundary "
                "is best-effort and accepted reduced isolation for this run"
            ),
        )
        records.append(override_record)
        _LOGGER.warning("sandbox override requested: %s", override_record.detail)

    drop_identity: tuple[int, int] | None = None
    if os.geteuid() == 0:
        drop_identity = _resolve_drop_identity()
        if drop_identity is None:
            records.append(
                DenialRecord(
                    kind="tier_fallback",
                    path="*",
                    worker_pid=os.getpid(),
                    detail=(
                        f"running as root but no {_DROP_USER!r} account exists; "
                        "unprivileged tier engaged (root cannot be DAC-constrained)"
                    ),
                )
            )
            _LOGGER.warning(
                "root detected but no %r account; using unprivileged tier",
                _DROP_USER,
            )

    workdir = Path(tempfile.mkdtemp(prefix="research-sandbox-"))
    try:
        with _ISOLATION_LOCK:
            _guard_layout(protected, data_root_path, workdir)
            staged = workdir / "partition"
            shutil.copytree(data_root_path, staged, dirs_exist_ok=True)
            if drop_identity is not None:
                exit_code, pid, stdout, stderr, tier_records = _run_privileged(
                    cmd, protected, workdir, staged, *drop_identity
                )
            else:
                exit_code, pid, stdout, stderr, tier_records = _run_unprivileged(
                    cmd, protected, workdir, staged
                )
            records.extend(tier_records)
            last_denials = list(records)
            last_run = RunResult(
                exit_code=exit_code,
                worker_pid=pid,
                stdout=stdout,
                stderr=stderr,
                records=tuple(records),
            )
        return exit_code
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
