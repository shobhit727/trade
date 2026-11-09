"""Evidence-driven candidate classifications for quantitative research outcomes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


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
