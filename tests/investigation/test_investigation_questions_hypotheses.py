"""Unit tests for InvestigationQuestion, InvestigationHypothesis, and EvidenceRequirement models."""

import pytest

from argus.investigation.evidence import EvidenceRequirement, EvidenceStatus
from argus.investigation.hypothesis import HypothesisStatus, InvestigationHypothesis
from argus.investigation.question import InvestigationQuestion, QuestionStatus, QuestionType


def test_question_creation_and_blocking():
    parent_q = InvestigationQuestion(
        question_text="What is Company A's primary legal entity?",
        question_type=QuestionType.ENTITY_DISCOVERY,
        priority=1.0,
        is_critical=True,
    )
    assert parent_q.status == QuestionStatus.OPEN

    child_q = InvestigationQuestion(
        question_text="What are Company A's operating subsidiaries?",
        question_type=QuestionType.RELATIONSHIP_VERIFICATION,
        parent_question_id=parent_q.question_id,
        dependencies=[parent_q.question_id],
    )
    # Child question is blocked until parent is resolved
    assert child_q.is_blocked(resolved_question_ids=set()) is True

    # When parent is resolved, child is unblocked
    assert child_q.is_blocked(resolved_question_ids={parent_q.question_id}) is False


def test_question_lifecycle_resolution():
    q = InvestigationQuestion(
        question_text="Who is the Chief Executive Officer?",
        question_type=QuestionType.OFFICER_TENURE,
    )
    q.mark_investigating()
    assert q.status == QuestionStatus.INVESTIGATING

    q.resolve(
        status=QuestionStatus.SUPPORTED,
        reason="Found Form 10-K signature block",
        claim_ids=["clm_123"],
    )
    assert q.status == QuestionStatus.SUPPORTED
    assert q.resolved_at is not None
    assert "clm_123" in q.resolved_by_claim_ids


def test_hypothesis_symmetrical_testing():
    hyp = InvestigationHypothesis(
        proposition="Subsidiary B is 100% owned by Parent A.",
        supporting_evidence_requirements=["Exhibit 21 schedule showing 100% ownership"],
        refuting_evidence_requirements=["Minority shareholder register or dissolution"],
    )
    assert hyp.current_status == HypothesisStatus.UNTESTED

    # Add supporting claims
    hyp.add_supporting_claim("clm_support_1", confidence_delta=0.40)
    hyp.add_supporting_claim("clm_support_2", confidence_delta=0.40)
    assert hyp.current_status == HypothesisStatus.SUPPORTED
    assert hyp.confidence >= 0.7

    # Add contradicting claim to test symmetrical scrutiny
    hyp.add_contradicting_claim("clm_contra_1")
    hyp.add_contradicting_claim("clm_contra_2")
    assert hyp.current_status == HypothesisStatus.CONTRADICTED


def test_evidence_requirement_satisfaction():
    req = EvidenceRequirement(
        description="Official certificate of incorporation from Delaware Division of Corporations",
        required_source_types=["official_registry", "regulatory_filing"],
        is_mandatory=True,
    )
    assert req.status == EvidenceStatus.UNSATISFIED

    req.add_satisfying_evidence(
        evidence_id="evi_delaware_01",
        source_type="official_registry",
        is_independent=True,
    )
    assert req.status == EvidenceStatus.SATISFIED
    assert "evi_delaware_01" in req.satisfied_by_evidence_ids
