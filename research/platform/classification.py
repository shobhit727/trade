"""Evidence-driven candidate classifications for quantitative research outcomes."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping


class CandidateClassification(StrEnum):
    """Research evidence labels; none of these implies real-money suitability."""

    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    OVERFIT = "overfit"
    TRAINING_ONLY = "training_only"
    VALIDATION_SUCCESS = "validation_success"
    HISTORICAL_OOS_SUCCESS = "historical_oos_success"
    ROBUST_RESEARCH_CANDIDATE = "robust_research_candidate"
    REQUIRES_INDEPENDENT_CONFIRMATION = "requires_independent_confirmation"


@dataclass(frozen=True, slots=True)
class CandidateEvidence:
    """Explicit evidence flags used to classify one research candidate.

    These are assertions supplied by a validated research protocol. This type deliberately
    defines no Sharpe, return, drawdown or trade-count thresholds.
    """

    failed: bool = False
    overfit_detected: bool | None = None
    train_evaluated: bool = False
    validation_selected: bool = False
    oos_evaluated: bool = False
    oos_passed: bool | None = None
    historical_or_exposed_oos: bool | None = None
    independent_confirmation: bool | None = None
    data_integrity_passed: bool | None = None
    robustness_passed: bool | None = None
    diagnostics_passed: bool | None = None

    def __post_init__(self) -> None:
        # Enforce three-valued evidence explicitly; unknown is never equivalent to a pass.
        for name in ("failed", "train_evaluated", "validation_selected", "oos_evaluated"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be a boolean")
        for name in (
            "overfit_detected",
            "oos_passed",
            "historical_or_exposed_oos",
            "independent_confirmation",
            "data_integrity_passed",
            "robustness_passed",
            "diagnostics_passed",
        ):
            value = getattr(self, name)
            if value is not None and not isinstance(value, bool):
                raise TypeError(f"{name} must be true, false or null")

    def to_dict(self) -> dict[str, Any]:
        # Preserve the exact evidence alongside the derived label.
        return asdict(self)


def classify_candidate(evidence: CandidateEvidence) -> CandidateClassification:
    """Derive the strongest justified research label without inventing thresholds."""
    # Explicit execution failure and explicit overfit evidence take precedence.
    if evidence.failed:
        return CandidateClassification.FAILED
    if evidence.overfit_detected is True:
        return CandidateClassification.OVERFIT
    if not evidence.train_evaluated:
        return CandidateClassification.INCONCLUSIVE
    if not evidence.validation_selected:
        return CandidateClassification.TRAINING_ONLY
    if not evidence.oos_evaluated:
        return CandidateClassification.VALIDATION_SUCCESS
    if evidence.oos_passed is None:
        return CandidateClassification.INCONCLUSIVE
    if evidence.oos_passed is False:
        return CandidateClassification.FAILED
    if evidence.historical_or_exposed_oos is True:
        return CandidateClassification.HISTORICAL_OOS_SUCCESS
    if evidence.independent_confirmation is not True:
        return CandidateClassification.REQUIRES_INDEPENDENT_CONFIRMATION
    if evidence.historical_or_exposed_oos is not False:
        return CandidateClassification.REQUIRES_INDEPENDENT_CONFIRMATION
    if (
        evidence.data_integrity_passed is not True
        or evidence.robustness_passed is not True
        or evidence.diagnostics_passed is not True
    ):
        return CandidateClassification.REQUIRES_INDEPENDENT_CONFIRMATION
    return CandidateClassification.ROBUST_RESEARCH_CANDIDATE


def classification_report(evidence: CandidateEvidence) -> dict[str, Any]:
    """Return the classification plus the evidence used to derive it."""
    # Keeping the evidence visible makes every unknown or incomplete gate auditable.
    return {
        "classification": classify_candidate(evidence).value,
        "classification_evidence": evidence.to_dict(),
    }


class OOSAcceptanceOutcome(StrEnum):
    """Explicit verdicts for one out-of-sample acceptance decision."""

    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"
    MISMATCH = "mismatch"


@dataclass(frozen=True, slots=True)
class OOSAcceptancePolicy:
    """Immutable, versioned OOS acceptance thresholds.

    A policy turns previously unknown OOS evidence into an explicit pass/fail verdict.
    Until a policy is configured, OOS results must remain unknown and inconclusive.
    """

    policy_version: str
    min_oos_sharpe: float
    min_oos_cagr: float
    min_oos_max_drawdown: float

    def __post_init__(self) -> None:
        if not isinstance(self.policy_version, str) or not self.policy_version.strip():
            raise ValueError("policy_version must be a non-empty string")
        for name in ("min_oos_sharpe", "min_oos_cagr", "min_oos_max_drawdown"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a real number")
            if not math.isfinite(float(value)):
                raise ValueError(f"{name} must be finite")

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_version": self.policy_version,
            "min_oos_sharpe": self.min_oos_sharpe,
            "min_oos_cagr": self.min_oos_cagr,
            "min_oos_max_drawdown": self.min_oos_max_drawdown,
        }


OOS_ACCEPTANCE_POLICY_V1 = OOSAcceptancePolicy(
    policy_version="v1-2026-11-10",
    min_oos_sharpe=0.0,
    min_oos_cagr=0.0,
    min_oos_max_drawdown=-0.35,
)

_APPROVED_OOS_POLICIES: MappingProxyType[str, OOSAcceptancePolicy] = MappingProxyType(
    {OOS_ACCEPTANCE_POLICY_V1.policy_version: OOS_ACCEPTANCE_POLICY_V1}
)


@dataclass(frozen=True, slots=True)
class OOSAcceptanceRecord:
    """Auditable verdict for one OOS evaluation under one policy version."""

    outcome: OOSAcceptanceOutcome
    policy_version: str | None
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, OOSAcceptanceOutcome):
            raise TypeError("outcome must be an OOSAcceptanceOutcome")
        if self.policy_version is not None and not isinstance(self.policy_version, str):
            raise TypeError("policy_version must be a string or None")
        for reason in self.reasons:
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError("reasons must contain non-empty strings")

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "policy_version": self.policy_version,
            "reasons": list(self.reasons),
        }


def evaluate_oos_acceptance(
    metrics: Mapping[str, Any],
    policy_version: str | None,
) -> OOSAcceptanceRecord:
    """Classify one OOS metric set against the approved, versioned acceptance policy.

    With ``policy_version=None`` (no approved policy configured) the verdict stays
    ``unknown``: unknown evidence is never promoted to a pass. A version that is not
    approved yields ``mismatch`` so unapproved policies can never silently pass.
    """
    if policy_version is None:
        return OOSAcceptanceRecord(
            outcome=OOSAcceptanceOutcome.UNKNOWN,
            policy_version=None,
            reasons=("no OOS acceptance policy is configured",),
        )
    if not isinstance(policy_version, str):
        raise TypeError("policy_version must be a string or None")
    policy = _APPROVED_OOS_POLICIES.get(policy_version)
    if policy is None:
        return OOSAcceptanceRecord(
            outcome=OOSAcceptanceOutcome.MISMATCH,
            policy_version=policy_version,
            reasons=(f"OOS acceptance policy version '{policy_version}' is not approved",),
        )
    reasons: list[str] = []
    # Metric producers (compute_portfolio_metrics) emit unprefixed names; the policy
    # speaks canonical oos_-prefixed names. The prefixed name wins when both exist.
    for name, threshold in (
        ("oos_sharpe", policy.min_oos_sharpe),
        ("oos_cagr", policy.min_oos_cagr),
        ("oos_max_drawdown", policy.min_oos_max_drawdown),
    ):
        alias = name.removeprefix("oos_")
        if name in metrics:
            value = metrics[name]
        elif alias in metrics:
            value = metrics[alias]
        else:
            reasons.append(f"missing required OOS metric '{name}'")
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            reasons.append(f"OOS metric '{name}' must be a real number")
            continue
        if not math.isfinite(float(value)):
            reasons.append(f"OOS metric '{name}' must be finite")
            continue
        if float(value) < threshold:
            reasons.append(
                f"OOS metric '{name}'={float(value)} is below the required minimum {threshold}"
            )
    outcome = OOSAcceptanceOutcome.FAIL if reasons else OOSAcceptanceOutcome.PASS
    return OOSAcceptanceRecord(
        outcome=outcome,
        policy_version=policy_version,
        reasons=tuple(reasons),
    )
