"""Tests for evidence-driven research candidate classifications."""

from __future__ import annotations

import pytest

from research.platform.classification import (
    CandidateClassification,
    CandidateEvidence,
    classify_candidate,
    classification_report,
)


def test_candidate_classification_covers_required_evidence_states() -> None:
    # Failed and overfit outcomes require explicit evidence, not inferred return thresholds.
    assert classify_candidate(CandidateEvidence(failed=True)) is CandidateClassification.FAILED
    assert classify_candidate(CandidateEvidence(overfit_detected=True)) is CandidateClassification.OVERFIT

    # Stage labels describe the furthest completed evidence stage.
    assert classify_candidate(CandidateEvidence(train_evaluated=True)) is CandidateClassification.TRAINING_ONLY
    assert classify_candidate(CandidateEvidence(
        train_evaluated=True,
        validation_selected=True,
    )) is CandidateClassification.VALIDATION_SUCCESS

    # OOS without an approved pass/fail gate remains inconclusive.
    assert classify_candidate(CandidateEvidence(
        train_evaluated=True,
        validation_selected=True,
        oos_evaluated=True,
        oos_passed=None,
    )) is CandidateClassification.INCONCLUSIVE
    assert classify_candidate(CandidateEvidence(
        train_evaluated=True,
        validation_selected=True,
        oos_evaluated=True,
        oos_passed=False,
    )) is CandidateClassification.FAILED


def test_candidate_classification_separates_historical_and_independent_oos() -> None:
    # A passed historical/exposed OOS result is not treated as a robust research candidate.
    historical = CandidateEvidence(
        train_evaluated=True,
        validation_selected=True,
        oos_evaluated=True,
        oos_passed=True,
        historical_or_exposed_oos=True,
    )
    assert classify_candidate(historical) is CandidateClassification.HISTORICAL_OOS_SUCCESS

    # A passed OOS result still needs independent confirmation and robustness evidence.
    unconfirmed = CandidateEvidence(
        train_evaluated=True,
        validation_selected=True,
        oos_evaluated=True,
        oos_passed=True,
        historical_or_exposed_oos=False,
        independent_confirmation=False,
    )
    assert classify_candidate(unconfirmed) is CandidateClassification.REQUIRES_INDEPENDENT_CONFIRMATION

    # Robust status requires every independent evidence gate to be explicitly true.
    robust = CandidateEvidence(
        train_evaluated=True,
        validation_selected=True,
        oos_evaluated=True,
        oos_passed=True,
        historical_or_exposed_oos=False,
        independent_confirmation=True,
        data_integrity_passed=True,
        robustness_passed=True,
        diagnostics_passed=True,
    )
    assert classify_candidate(robust) is CandidateClassification.ROBUST_RESEARCH_CANDIDATE


def test_classification_report_preserves_unknown_evidence() -> None:
    # The result exposes both the label and the exact evidence used to derive it.
    evidence = CandidateEvidence(
        train_evaluated=True,
        validation_selected=True,
        oos_evaluated=True,
        oos_passed=None,
    )
    report = classification_report(evidence)
    assert report["classification"] == "inconclusive"
    assert report["classification_evidence"]["oos_passed"] is None
    assert report["classification_evidence"]["historical_or_exposed_oos"] is None


def test_candidate_evidence_rejects_non_boolean_gate_values() -> None:
    # Strings cannot be coerced into positive evidence.
    with pytest.raises(TypeError, match="oos_passed"):
        CandidateEvidence(oos_passed="passed")


