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




# --- F-001 / CR-001: versioned OOS acceptance policy -------------------------


from research.platform.classification import (
    OOS_ACCEPTANCE_POLICY_V1,
    OOSAcceptanceOutcome,
    OOSAcceptancePolicy,
    OOSAcceptanceRecord,
    evaluate_oos_acceptance,
)


def test_oos_acceptance_policy_is_frozen_and_versioned() -> None:
    # The single approved policy version pins the exact thresholds.
    assert OOS_ACCEPTANCE_POLICY_V1.policy_version == "v1-2026-11-10"
    assert OOS_ACCEPTANCE_POLICY_V1.min_oos_sharpe == 0.0
    assert OOS_ACCEPTANCE_POLICY_V1.min_oos_cagr == 0.0
    assert OOS_ACCEPTANCE_POLICY_V1.min_oos_max_drawdown == -0.35
    dataclass_fields = OOSAcceptancePolicy.__dataclass_fields__
    assert dataclass_fields["min_oos_sharpe"].type is not None
    with pytest.raises((AttributeError, TypeError)):
        OOS_ACCEPTANCE_POLICY_V1.min_oos_sharpe = 1.0  # type: ignore[misc]


def test_oos_acceptance_policy_rejects_invalid_configuration() -> None:
    # A version string and finite thresholds are required for approval.
    with pytest.raises(ValueError, match="policy_version"):
        OOSAcceptancePolicy("  ", 0.0, 0.0, -0.35)
    with pytest.raises(TypeError, match="min_oos_sharpe"):
        OOSAcceptancePolicy("v2", "1.0", 0.0, -0.35)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="min_oos_sharpe"):
        OOSAcceptancePolicy("v2", float("nan"), 0.0, -0.35)
    with pytest.raises(ValueError, match="min_oos_max_drawdown"):
        OOSAcceptancePolicy("v2", 0.0, 0.0, float("inf"))


def test_oos_acceptance_without_policy_remains_unknown() -> None:
    # No approved policy means the OOS result stays unknown, never a pass.
    record = evaluate_oos_acceptance({"oos_sharpe": 2.0, "oos_cagr": 0.4, "oos_max_drawdown": -0.05}, None)
    assert isinstance(record, OOSAcceptanceRecord)
    assert record.outcome is OOSAcceptanceOutcome.UNKNOWN
    assert record.policy_version is None
    assert record.reasons
    payload = record.to_dict()
    assert payload["outcome"] == "unknown"
    assert payload["policy_version"] is None


def test_oos_acceptance_classifies_passing_metrics() -> None:
    # Every threshold met exactly at the boundary still passes.
    record = evaluate_oos_acceptance(
        {"oos_sharpe": 0.0, "oos_cagr": 0.0, "oos_max_drawdown": -0.35},
        OOS_ACCEPTANCE_POLICY_V1.policy_version,
    )
    assert record.outcome is OOSAcceptanceOutcome.PASS
    assert record.policy_version == "v1-2026-11-10"
    assert record.reasons == ()
    assert record.to_dict() == {
        "outcome": "pass",
        "policy_version": "v1-2026-11-10",
        "reasons": [],
    }


def test_oos_acceptance_classifies_each_failed_threshold() -> None:
    # A breach of any single threshold fails with a precise reason.
    sharpe = evaluate_oos_acceptance(
        {"oos_sharpe": -0.01, "oos_cagr": 0.1, "oos_max_drawdown": -0.1},
        OOS_ACCEPTANCE_POLICY_V1.policy_version,
    )
    assert sharpe.outcome is OOSAcceptanceOutcome.FAIL
    assert "'oos_sharpe'" in sharpe.reasons[0]

    cagr = evaluate_oos_acceptance(
        {"oos_sharpe": 1.0, "oos_cagr": -0.02, "oos_max_drawdown": -0.1},
        OOS_ACCEPTANCE_POLICY_V1.policy_version,
    )
    assert cagr.outcome is OOSAcceptanceOutcome.FAIL
    assert any("'oos_cagr'" in reason for reason in cagr.reasons)

    drawdown = evaluate_oos_acceptance(
        {"oos_sharpe": 1.0, "oos_cagr": 0.1, "oos_max_drawdown": -0.36},
        OOS_ACCEPTANCE_POLICY_V1.policy_version,
    )
    assert drawdown.outcome is OOSAcceptanceOutcome.FAIL
    assert any("'oos_max_drawdown'" in reason for reason in drawdown.reasons)


def test_oos_acceptance_fails_on_missing_metrics() -> None:
    # Missing required metrics cannot satisfy the policy by absence.
    record = evaluate_oos_acceptance({"oos_sharpe": 1.0}, OOS_ACCEPTANCE_POLICY_V1.policy_version)
    assert record.outcome is OOSAcceptanceOutcome.FAIL
    assert sorted(record.reasons) == [
        "missing required OOS metric 'oos_cagr'",
        "missing required OOS metric 'oos_max_drawdown'",
    ]


def test_oos_acceptance_fails_on_nonfinite_metrics() -> None:
    # NaN and infinity are not evidence; they fail rather than compare.
    nan_record = evaluate_oos_acceptance(
        {"oos_sharpe": float("nan"), "oos_cagr": 0.1, "oos_max_drawdown": -0.1},
        OOS_ACCEPTANCE_POLICY_V1.policy_version,
    )
    assert nan_record.outcome is OOSAcceptanceOutcome.FAIL
    assert any("finite" in reason for reason in nan_record.reasons)

    inf_record = evaluate_oos_acceptance(
        {"oos_sharpe": float("inf"), "oos_cagr": 0.1, "oos_max_drawdown": -0.1},
        OOS_ACCEPTANCE_POLICY_V1.policy_version,
    )
    assert inf_record.outcome is OOSAcceptanceOutcome.FAIL
    assert any("finite" in reason for reason in inf_record.reasons)


def test_oos_acceptance_fails_on_nonnumeric_metric_values() -> None:
    # Strings cannot masquerade as measured performance.
    record = evaluate_oos_acceptance(
        {"oos_sharpe": "1.0", "oos_cagr": 0.1, "oos_max_drawdown": -0.1},
        OOS_ACCEPTANCE_POLICY_V1.policy_version,
    )
    assert record.outcome is OOSAcceptanceOutcome.FAIL
    assert any("real number" in reason for reason in record.reasons)


def test_oos_acceptance_rejects_unapproved_policy_version_as_mismatch() -> None:
    # An unapproved version must surface as an explicit mismatch, never silently pass.
    record = evaluate_oos_acceptance(
        {"oos_sharpe": 9.0, "oos_cagr": 9.0, "oos_max_drawdown": -0.01},
        "v0-never-approved",
    )
    assert record.outcome is OOSAcceptanceOutcome.MISMATCH
    assert record.policy_version == "v0-never-approved"
    assert record.reasons
    payload = record.to_dict()
    assert payload["outcome"] == "mismatch"
    assert payload["policy_version"] == "v0-never-approved"


def test_oos_acceptance_accepts_unprefixed_producer_metrics() -> None:
    # compute_portfolio_metrics emits unprefixed names; the policy must read them.
    # A strongly profitable equity curve classifies as a pass, not a spurious fail.
    profitable = {"sharpe": 1.4, "cagr": 0.12, "max_drawdown": -0.08}
    record = evaluate_oos_acceptance(profitable, OOS_ACCEPTANCE_POLICY_V1.policy_version)
    assert record.outcome is OOSAcceptanceOutcome.PASS
    assert record.reasons == ()

    # Alias lookup still enforces each threshold: a real drawdown breach fails.
    breach = {"sharpe": 1.4, "cagr": 0.12, "max_drawdown": -0.4}
    failing = evaluate_oos_acceptance(breach, OOS_ACCEPTANCE_POLICY_V1.policy_version)
    assert failing.outcome is OOSAcceptanceOutcome.FAIL
    assert "'oos_max_drawdown'=-0.4" in failing.reasons[0]

    # Non-finite unprefixed metrics fail rather than compare.
    nonfinite = evaluate_oos_acceptance(
        {"sharpe": float("nan"), "cagr": 0.1, "max_drawdown": -0.1},
        OOS_ACCEPTANCE_POLICY_V1.policy_version,
    )
    assert nonfinite.outcome is OOSAcceptanceOutcome.FAIL
    assert any("finite" in reason for reason in nonfinite.reasons)


def test_oos_acceptance_prefixed_metric_wins_on_conflict() -> None:
    # When both spellings exist the canonical prefixed value governs the verdict.
    record = evaluate_oos_acceptance(
        {"oos_sharpe": -1.0, "sharpe": 5.0, "oos_cagr": 0.1, "oos_max_drawdown": -0.1},
        OOS_ACCEPTANCE_POLICY_V1.policy_version,
    )
    assert record.outcome is OOSAcceptanceOutcome.FAIL
    assert "'oos_sharpe'=-1.0" in record.reasons[0]


def test_oos_acceptance_record_validates_construction() -> None:
    # The record itself rejects malformed verdicts and reasons.
    with pytest.raises(TypeError, match="outcome"):
        OOSAcceptanceRecord("pass", "v1-2026-11-10", ())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="reasons"):
        OOSAcceptanceRecord(OOSAcceptanceOutcome.PASS, "v1-2026-11-10", ("",))
