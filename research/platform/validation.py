"""Chronological split policy and guarded evaluation lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum


class Partition(StrEnum):
    """Chronological data partitions used by candidate research."""

    TRAIN = "train"
    VALIDATION = "validation"
    OOS = "out_of_sample"
    FINAL_HOLDOUT = "final_holdout"


class AccessRole(StrEnum):
    """Capabilities granted to distinct research pipeline stages."""

    OPTIMIZER = "optimizer"
    MODEL_SELECTOR = "model_selector"
    OOS_EVALUATOR = "oos_evaluator"
    FINAL_AUDITOR = "final_auditor"


class EvaluationState(StrEnum):
    """One-way state machine for protecting out-of-sample information."""

    DISCOVERY = "discovery"
    CANDIDATE_FROZEN = "candidate_frozen"
    OOS_EVALUATING = "oos_evaluating"
    OOS_RECORDED = "oos_recorded"
    HOLDOUT_OPENED = "holdout_opened"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class TimeWindow:
    """Half-open chronological interval [start, end)."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        # Half-open intervals prevent boundary timestamps being assigned twice.
        if (self.start.tzinfo is None or self.start.utcoffset() is None
                or self.end.tzinfo is None or self.end.utcoffset() is None):
            raise ValueError("window timestamps must be timezone-aware")
        if self.end <= self.start:
            raise ValueError("window end must follow start")


@dataclass(frozen=True, slots=True)
class SplitPlan:
    """Time-ordered partitions plus an explicit embargo between each partition."""

    train: TimeWindow
    validation: TimeWindow
    oos: TimeWindow
    final_holdout: TimeWindow
    embargo: timedelta = timedelta(0)
    protocol_id: str = "chronological-v1"
    historical_test_exposed: bool = False

    def __post_init__(self) -> None:
        # Validate strict chronology and enforce a non-negative purge/embargo gap.
        if self.embargo < timedelta(0):
            raise ValueError("embargo cannot be negative")
        windows = (self.train, self.validation, self.oos, self.final_holdout)
        for previous, current in zip(windows, windows[1:]):
            if previous.end + self.embargo > current.start:
                raise ValueError("partitions overlap or do not respect the embargo")
        if not self.protocol_id.strip():
            raise ValueError("protocol_id is required")



@dataclass(slots=True)
class ValidationLifecycle:
    """Enforce freeze-before-OOS and one-time final-holdout opening."""

    state: EvaluationState = EvaluationState.DISCOVERY
    candidate_digest: str | None = None
    oos_passed: bool | None = None
    oos_evaluation_id: str | None = None
    holdout_access_count: int = 0
    events: list[dict[str, str]] = field(default_factory=list)

    def authorize(self, role: AccessRole, partition: Partition) -> None:
        """Raise PermissionError when a pipeline stage requests a protected partition."""
        # Optimisation sees TRAIN only; validation is reserved for explicit model selection.
        permissions = {
            AccessRole.OPTIMIZER: {Partition.TRAIN},
            AccessRole.MODEL_SELECTOR: {Partition.TRAIN, Partition.VALIDATION},
            AccessRole.OOS_EVALUATOR: {Partition.OOS},
            AccessRole.FINAL_AUDITOR: {Partition.FINAL_HOLDOUT},
        }
        if partition not in permissions[role]:
            raise PermissionError(f"{role.value} cannot access {partition.value}")
        if role in {AccessRole.OPTIMIZER, AccessRole.MODEL_SELECTOR} and self.state is not EvaluationState.DISCOVERY:
            raise PermissionError("discovery access closes when the candidate is frozen")
        if role is AccessRole.OOS_EVALUATOR:
            if self.state is not EvaluationState.CANDIDATE_FROZEN:
                raise PermissionError("OOS evaluation is permitted once after candidate freeze")
            self.state = EvaluationState.OOS_EVALUATING
            self.events.append({"event": "oos_evaluation_started", "candidate_digest": self.candidate_digest or ""})
        if role is AccessRole.FINAL_AUDITOR:
            if self.state is not EvaluationState.HOLDOUT_OPENED:
                raise PermissionError("final holdout is sealed until explicitly unlocked")
            if self.holdout_access_count != 0:
                raise PermissionError("final holdout data may be opened only once")
            self.holdout_access_count = 1

    def freeze_candidate(self, candidate_digest: str) -> None:
        """Freeze the sole candidate before any OOS evaluation can take place."""
        # The frozen digest is immutable and cannot be replaced after evaluation starts.
        if self.state is not EvaluationState.DISCOVERY:
            raise RuntimeError("candidate can only be frozen once during discovery")
        if len(candidate_digest) < 16:
            raise ValueError("candidate_digest must be a stable cryptographic fingerprint")
        self.candidate_digest = candidate_digest
        self.state = EvaluationState.CANDIDATE_FROZEN
        self.events.append({"event": "candidate_frozen", "candidate_digest": candidate_digest})

    def record_oos(self, evaluation_id: str, passed: bool) -> None:
        """Record one OOS result for the frozen candidate; no repeated tuning loop."""
        # An OOS failure is still recorded and cannot be used to select a new candidate.
        if self.state is not EvaluationState.OOS_EVALUATING:
            raise RuntimeError("OOS result requires the single authorised OOS evaluation")
        if not evaluation_id.strip():
            raise ValueError("evaluation_id is required")
        self.oos_evaluation_id = evaluation_id
        self.oos_passed = bool(passed)
        self.state = EvaluationState.OOS_RECORDED
        self.events.append({"event": "oos_recorded", "evaluation_id": evaluation_id,
                            "passed": str(bool(passed)).lower()})

    def open_final_holdout(self, approval_reference: str) -> None:
        """Unlock final holdout exactly once and only after a passing OOS evaluation."""
        # A failed OOS result cannot be rescued by repeatedly opening the final holdout.
        if self.state is not EvaluationState.OOS_RECORDED or self.oos_passed is not True:
            raise PermissionError("final holdout requires a passing recorded OOS evaluation")
        if not approval_reference.strip() or self.holdout_access_count != 0:
            raise PermissionError("holdout approval must be supplied once")
        self.state = EvaluationState.HOLDOUT_OPENED
        self.events.append({"event": "holdout_opened", "approval_reference": approval_reference})

    def complete(self, passed: bool) -> None:
        """Close the research lifecycle after the final audit has been recorded."""
        # Completion requires the holdout to have been opened under the audited policy.
        if self.state is not EvaluationState.HOLDOUT_OPENED or self.holdout_access_count != 1:
            raise RuntimeError("lifecycle requires one final holdout review")
        self.state = EvaluationState.COMPLETED
        self.events.append({"event": "completed", "passed": str(bool(passed)).lower()})
