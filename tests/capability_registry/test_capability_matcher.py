"""Unit tests for CapabilityMatcher requirement-based matching and ranking."""

import pytest

from argus.capability_registry.defaults import get_default_capabilities
from argus.capability_registry.matcher import CapabilityMatcher
from argus.capability_registry.models import HealthStatus
from argus.capability_registry.registry import CapabilityRegistry
from argus.investigation.question import InvestigationQuestion, QuestionType


@pytest.fixture
def registry() -> CapabilityRegistry:
    reg = CapabilityRegistry()
    for cap in get_default_capabilities():
        reg.register(cap, overwrite=True)
    return reg


@pytest.fixture
def matcher() -> CapabilityMatcher:
    return CapabilityMatcher()


def test_matcher_evidence_requirement_matching(registry: CapabilityRegistry, matcher: CapabilityMatcher):
    """Verify evidence requirements drive capability selection."""
    q_corp = InvestigationQuestion(
        question_text="Determine company officers and statutory registration number.",
        question_type=QuestionType.OFFICER_TENURE,
        required_evidence=["Companies House statutory register of directors"],
        related_entities=["AeroDynamics UK Limited"],
    )
    cands = matcher.match(q_corp, capabilities=registry.list())
    assert len(cands) >= 1
    assert cands[0].capability_id == "corporate_registry_intelligence"
    assert cands[0].match_score > 0.80


def test_matcher_infrastructure_dns(registry: CapabilityRegistry, matcher: CapabilityMatcher):
    """Verify DNS and SAN evidence selects infrastructure capability."""
    q_infra = InvestigationQuestion(
        question_text="Trace subdomains and CT certificate logs for aerospace-uk.com.",
        question_type=QuestionType.INFRASTRUCTURE_ATTRIBUTION,
        required_evidence=["DNS MX and A record resolution", "Certificate Transparency CT log SAN entry"],
        related_entities=["aerospace-uk.com"],
    )
    cands = matcher.match(q_infra, capabilities=registry.list())
    assert len(cands) >= 1
    assert cands[0].capability_id == "infrastructure_discovery"


def test_matcher_unavailable_exclusion(registry: CapabilityRegistry, matcher: CapabilityMatcher):
    """Verify DISABLED or UNAVAILABLE capabilities are excluded."""
    registry.disable("corporate_registry_intelligence")

    q = InvestigationQuestion(
        question_text="Check Companies House filing for target company.",
        question_type=QuestionType.ENTITY_DISCOVERY,
        required_evidence=["Companies House filing"],
        related_entities=["Target Corp"],
    )
    cands = matcher.match(q, capabilities=registry.list())
    selected_caps = [c.capability_id for c in cands]
    assert "corporate_registry_intelligence" not in selected_caps
    # Fallback to general research
    assert "general_web_research" in selected_caps


def test_matcher_degraded_capability_handling(registry: CapabilityRegistry, matcher: CapabilityMatcher):
    """Verify DEGRADED capability remains selectable but is penalized with risk flags."""
    registry.degrade("identity_resolution")

    q = InvestigationQuestion(
        question_text="Identify developer behind GitHub handle.",
        question_type=QuestionType.IDENTITY_CORRELATION,
        required_evidence=["GitHub developer profile"],
        related_entities=["dev_user"],
    )
    cands = matcher.match(q, capabilities=registry.list())
    assert len(cands) >= 1
    top = cands[0]
    assert top.capability_id == "identity_resolution"
    assert any("DEGRADED" in rf for rf in top.risk_flags)


def test_matcher_multiple_implementation_competition(registry: CapabilityRegistry, matcher: CapabilityMatcher):
    """Verify two implementations of the same capability are ranked deterministically."""
    q = InvestigationQuestion(
        question_text="Resolve developer username 'vkroll' with PGP key proof.",
        question_type=QuestionType.IDENTITY_CORRELATION,
        required_evidence=["Keybase proof and PGP signed assertion"],
        related_entities=["vkroll"],
    )
    cands = matcher.match(q, capabilities=registry.list())
    ident_cands = [c for c in cands if c.capability_id == "identity_resolution"]
    assert len(ident_cands) >= 2
    # Both implementations returned
    impl_ids = [c.implementation_id for c in ident_cands]
    assert "impl_challenger_identity_specialist_v2" in impl_ids
    assert "impl_identity_probe_specialist_v1" in impl_ids
    # Deterministic ranking order: Challenger ranked top due to higher F1 and PGP match
    assert ident_cands[0].implementation_id == "impl_challenger_identity_specialist_v2"


def test_matcher_jurisdiction_matching(registry: CapabilityRegistry, matcher: CapabilityMatcher):
    """Verify jurisdiction fit boosts candidate ranking and populates jurisdiction_fit."""
    q_uk = InvestigationQuestion(
        question_text="Examine UK registrar filings for London subsidiary.",
        question_type=QuestionType.ENTITY_DISCOVERY,
        required_evidence=["Companies House annual report"],
        related_entities=["UK Sub Ltd"],
        temporal_context={"jurisdiction": "GB"},
    )
    cands = matcher.match(q_uk, capabilities=registry.list())
    assert len(cands) >= 1
    top = cands[0]
    assert top.capability_id == "corporate_registry_intelligence"
    assert top.jurisdiction_fit > 0.0


def test_matcher_temporal_matching(registry: CapabilityRegistry, matcher: CapabilityMatcher):
    """Verify temporal requirements and historical as_of_date enhance temporal_fit score."""
    q_hist = InvestigationQuestion(
        question_text="Determine board membership as of 2019-12-31 prior to acquisition.",
        question_type=QuestionType.OFFICER_TENURE,
        required_evidence=["Historical board appointment register 2019"],
        related_entities=["OldCorp"],
        temporal_context={"as_of_date": "2019-12-31"},
    )
    cands = matcher.match(q_hist, capabilities=registry.list())
    assert len(cands) >= 1
    corp_cand = next(c for c in cands if c.capability_id == "corporate_registry_intelligence")
    assert corp_cand.temporal_fit > 0.0

