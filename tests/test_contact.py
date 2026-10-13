"""Unit tests for Phase 4: Tiered Contact Resolution Engine."""

from unittest.mock import AsyncMock, patch

import pytest

from argus.contact.resolver import ContactResolutionEngine
from argus.domain.claim import ClaimStatus
from argus.domain.entity import Entity
from argus.domain.event import EventType
from argus.domain.objective import ResearchObjective
from argus.storage.db import DatabaseManager
from argus.storage.repository import ArgusRepository


def test_email_pattern_inference_schemas():
    """Exit Criterion 1: Corporate email pattern inference generates correct addresses."""
    engine = ContactResolutionEngine()

    # Case A: Standard first.last
    email1 = engine.infer_email("John Doe", "ford.com", pattern="{first}.{last}")
    assert email1 == "john.doe@ford.com"

    # Case B: First initial + last
    email2 = engine.infer_email("John Doe", "ford.com", pattern="{f}{last}")
    assert email2 == "jdoe@ford.com"

    # Case C: Name with professional titles and middle initials
    email3 = engine.infer_email("Dr. Jane M. Watson, PhD", "pfizer.com", pattern="{first}.{last}")
    assert email3 == "jane.watson@pfizer.com"

    # Case D: Underscore pattern
    email4 = engine.infer_email("Robert Smith", "bhp.com", pattern="{first}_{last}")
    assert email4 == "robert_smith@bhp.com"

    # Case E: Domain normalization (stripping www. and email prefix)
    email5 = engine.infer_email("Alice Cooper", "www.example.org", pattern="{first}.{last}")
    assert email5 == "alice.cooper@example.org"


def test_detect_email_pattern_from_examples():
    """Detect dominant email schema from sample public addresses."""
    engine = ContactResolutionEngine()

    samples_dot = [
        "media.inquiries@ford.com",
        "john.smith@ford.com",
        "mary.jane@ford.com",
    ]
    pattern1 = engine.detect_email_pattern_from_examples(samples_dot, target_domain="ford.com")
    assert pattern1 == "{first}.{last}"

    samples_underscore = [
        "john_smith@company.com",
        "mary_jane@company.com",
    ]
    pattern2 = engine.detect_email_pattern_from_examples(samples_underscore, target_domain="company.com")
    assert pattern2 == "{first}_{last}"


@pytest.mark.asyncio
async def test_async_dns_mx_verification():
    """Exit Criterion 1: Verify domain MX records via asynchronous DNS."""
    engine = ContactResolutionEngine()

    # Mocked valid MX resolution
    mock_mx_answer = [object()]
    with patch("dns.asyncresolver.Resolver.resolve", new_callable=AsyncMock, return_value=mock_mx_answer):
        is_valid = await engine.verify_domain_mx("ford.com")
        assert is_valid is True

    # Mocked MX resolution failure
    with patch("dns.asyncresolver.Resolver.resolve", new_callable=AsyncMock, side_effect=Exception("NXDOMAIN")):
        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.getaddrinfo = AsyncMock(side_effect=Exception("Failed"))
            is_invalid = await engine.verify_domain_mx("nonexistent-domain-xyz-12345.corp")
            assert is_invalid is False


def test_facility_switchboard_and_media_capture():
    """Exit Criterion 2: Extract official switchboard and media contacts with correct predicates."""
    engine = ContactResolutionEngine()

    text_content = (
        "Kentucky Truck Plant\n"
        "Plant Switchboard: (502) 429-2000\n"
        "Plant Manager: John Doe\n"
        "For media inquiries and press relations, call +1 313-845-8540."
    )

    results = engine.extract_switchboard_numbers(text_content)
    assert len(results) >= 2

    # Verify switchboard line
    facility_line = next(r for r in results if r["predicate"] == "HAS_FACILITY_PHONE")
    assert facility_line["phone"] == "(502) 429-2000"

    # Verify media line
    media_line = next(r for r in results if r["predicate"] == "HAS_MEDIA_CONTACT")
    assert media_line["phone"] == "(313) 845-8540"


@pytest.mark.asyncio
async def test_resolve_contacts_for_objective():
    """Exit Criteria 3: Claims carry confidence=0.85 and is_inferred=True metadata."""
    repo = ArgusRepository(DatabaseManager(":memory:"))
    engine = ContactResolutionEngine()

    obj_id = "obj_contact_test"

    # Create company and person entities
    company = Entity(
        objective_id=obj_id,
        entity_type="company",
        canonical_name="Ford Motor Company",
    )
    person = Entity(
        objective_id=obj_id,
        entity_type="person",
        canonical_name="Mark Smith",
    )
    repo.save_objective(
        ResearchObjective(
            objective_id=obj_id,
            target="Ford",
            target_type="company",
            intelligence_goal="test",
            required_fields=["email"],
            success_criteria="test",
            max_tasks=5,
        )
    )
    repo.save_entity(company)
    repo.save_entity(person)

    with patch.object(engine, "verify_domain_mx", new_callable=AsyncMock, return_value=True):
        claims = await engine.resolve_contacts_for_objective(
            objective_id=obj_id,
            repo=repo,
            default_domain="ford.com",
        )

    assert len(claims) == 1
    claim = claims[0]
    assert claim.subject_entity_id == person.entity_id
    assert claim.predicate == "HAS_EMAIL"
    assert claim.object_value == "mark.smith@ford.com"
    assert claim.confidence == 0.85
    assert claim.status == ClaimStatus.INFERRED
    assert claim.derivation_method == "corporate_email_pattern"
    assert claim.evidence_ids == []

    # Check updated entity attributes
    updated_person = next(e for e in repo.list_entities(obj_id) if e.entity_id == person.entity_id)
    assert updated_person.attributes.get("email") == "mark.smith@ford.com"
    assert updated_person.attributes.get("is_inferred") is True

    # Check audit trail event
    events = repo.list_events(obj_id)
    claim_events = [e for e in events if e.event_type == EventType.CLAIM_CREATED]
    assert len(claim_events) >= 1
    assert claim_events[0].payload.get("is_inferred") is True
    assert claim_events[0].payload.get("confidence") == 0.85


def test_infer_company_domain():
    """Verify company and URL domain inference for various automotive OEMs."""
    engine = ContactResolutionEngine()
    assert engine.infer_company_domain("General Motors Company") == "gm.com"
    assert engine.infer_company_domain("https://media.gm.com/article123") == "gm.com"
    assert engine.infer_company_domain("Ford Motor Co.") == "ford.com"
    assert engine.infer_company_domain("https://media.ford.com/press") == "ford.com"
    assert engine.infer_company_domain("Stellantis North America") == "stellantis.com"
    assert engine.infer_company_domain("https://media.stellantisnorthamerica.com") == "stellantis.com"
    assert engine.infer_company_domain("Tesla Inc") == "tesla.com"


@pytest.mark.asyncio
async def test_resolve_document_contacts_realtime():
    """Real-time document contact resolution binds switchboard numbers to mentioned facilities."""
    from argus.crawler.models import Document

    repo = ArgusRepository(DatabaseManager(":memory:"))
    engine = ContactResolutionEngine()
    obj_id = "obj_doc_contact"
    repo.save_objective(
        ResearchObjective(
            objective_id=obj_id,
            target="GM",
            target_type="company",
            intelligence_goal="test",
            required_fields=["facility_phone"],
            success_criteria="test",
        )
    )

    plant = Entity(
        objective_id=obj_id,
        entity_type="manufacturing_plant",
        canonical_name="Bowling Green Assembly",
    )
    repo.save_entity(plant)

    doc = Document(
        url="https://media.gm.com/bowling-green",
        title="Bowling Green Facility Overview",
        text_content=(
            "General Motors Bowling Green Assembly Plant.\n"
            "Main Plant Switchboard: (270) 793-2000\n"
            "Facility produces Chevrolet Corvette."
        ),
        status_code=200,
    )

    claims = await engine.resolve_document_contacts(doc=doc, objective_id=obj_id, repo=repo)
    assert len(claims) == 1
    assert claims[0].predicate == "HAS_FACILITY_PHONE"
    assert claims[0].object_value == "(270) 793-2000"

    # Facility attributes should be updated
    updated_plant = repo.get_entity(plant.entity_id)
    assert updated_plant.attributes.get("facility_phone") == "(270) 793-2000"


@pytest.mark.asyncio
async def test_resolve_entity_contacts_realtime():
    """Real-time entity contact resolution infers corporate email for personnel linked to plant."""
    from argus.domain.claim import Claim

    repo = ArgusRepository(DatabaseManager(":memory:"))
    engine = ContactResolutionEngine()
    obj_id = "obj_ent_realtime"
    repo.save_objective(
        ResearchObjective(
            objective_id=obj_id,
            target="GM",
            target_type="company",
            intelligence_goal="test",
            required_fields=["email"],
            success_criteria="test",
        )
    )

    company = Entity(
        objective_id=obj_id,
        entity_type="company",
        canonical_name="General Motors",
    )
    plant = Entity(
        objective_id=obj_id,
        entity_type="manufacturing_plant",
        canonical_name="Tonawanda Engine",
    )
    person = Entity(
        objective_id=obj_id,
        entity_type="person",
        canonical_name="Ram Ramanujam",
    )
    repo.save_entity(company)
    repo.save_entity(plant)
    repo.save_entity(person)

    # Claim linking person to plant
    claim_mgr = Claim(
        objective_id=obj_id,
        subject_entity_id=plant.entity_id,
        predicate="HAS_PLANT_MANAGER",
        object_value="Ram Ramanujam",
        object_entity_id=person.entity_id,
        status=ClaimStatus.SUPPORTED,
    )
    # Claim linking plant to company
    claim_op = Claim(
        objective_id=obj_id,
        subject_entity_id=plant.entity_id,
        predicate="OPERATED_BY",
        object_value="General Motors",
        object_entity_id=company.entity_id,
        status=ClaimStatus.SUPPORTED,
    )
    repo.save_claim(claim_mgr)
    repo.save_claim(claim_op)

    with patch.object(engine, "verify_domain_mx", new_callable=AsyncMock, return_value=True):
        claims = await engine.resolve_entity_contacts_realtime(objective_id=obj_id, repo=repo)

    assert len(claims) == 1
    assert claims[0].predicate == "HAS_EMAIL"
    assert claims[0].object_value == "ram.ramanujam@gm.com"
    assert claims[0].status == ClaimStatus.INFERRED
    assert claims[0].derivation_method == "corporate_email_pattern"
    assert claims[0].evidence_ids == []

    # Check updated entity attributes
    updated_person = repo.get_entity(person.entity_id)
    assert updated_person.attributes.get("email") == "ram.ramanujam@gm.com"


def test_materialize_plant_leadership_matrix():
    """Repository autonomously materializes clean human-readable matrix with zero raw UUIDs."""
    from argus.domain.claim import Claim
    from argus.domain.evidence import Evidence

    repo = ArgusRepository(DatabaseManager(":memory:"))
    obj_id = "obj_matrix_test"
    repo.save_objective(
        ResearchObjective(
            objective_id=obj_id,
            target="Auto",
            target_type="industry",
            intelligence_goal="test",
            required_fields=["plant"],
            success_criteria="test",
        )
    )

    plant = Entity(
        objective_id=obj_id,
        entity_type="manufacturing_plant",
        canonical_name="Tonawanda Engine Plant",
        attributes={"location": "2995 River Rd, Buffalo, NY"},
    )
    director = Entity(
        objective_id=obj_id,
        entity_type="person",
        canonical_name="Ram Ramanujam",
        attributes={"email": "ram.ramanujam@gm.com", "phone": "(716) 879-5000 ext. 101"},
    )
    tech_lead = Entity(
        objective_id=obj_id,
        entity_type="person",
        canonical_name="Sarah Connor",
        attributes={"email": "sarah.connor@gm.com", "phone": "(716) 879-5000 ext. 210"},
    )
    repo.save_entity(plant)
    repo.save_entity(director)
    repo.save_entity(tech_lead)

    ev = Evidence(
        source_id="news_source",
        url="https://media.gm.com/tonawanda-announcement",
        passage="Leadership confirmed at Tonawanda Engine.",
        confidence=0.95,
    )
    repo.save_evidence(ev)

    # Claims
    claims = [
        Claim(
            objective_id=obj_id,
            subject_entity_id=plant.entity_id,
            predicate="HAS_PLANT_MANAGER",
            object_value="Ram Ramanujam",
            object_entity_id=director.entity_id,
            status=ClaimStatus.SUPPORTED,
            evidence_ids=[ev.evidence_id],
        ),
        Claim(
            objective_id=obj_id,
            subject_entity_id=plant.entity_id,
            predicate="HAS_TECH_LEAD",
            object_value="Sarah Connor",
            object_entity_id=tech_lead.entity_id,
            status=ClaimStatus.SUPPORTED,
            evidence_ids=[ev.evidence_id],
        ),
        Claim(
            objective_id=obj_id,
            subject_entity_id=plant.entity_id,
            predicate="HAS_FACILITY_PHONE",
            object_value="(716) 879-5000",
            status=ClaimStatus.SUPPORTED,
            evidence_ids=[ev.evidence_id],
        ),
    ]
    for c in claims:
        repo.save_claim(c)

    # Materialize matrix autonomously
    count = repo.materialize_plant_leadership_matrix(objective_id=obj_id)
    assert count == 1

    # Verify rows in plant_leadership_matrix table
    with repo.db.transaction() as cur:
        cur.execute("SELECT * FROM plant_leadership_matrix WHERE plant_name = ?", ("Tonawanda Engine Plant",))
        row = cur.fetchone()
        assert row is not None
        assert row["plant_name"] == "Tonawanda Engine Plant"
        assert row["plant_location"] == "2995 River Rd, Buffalo, NY"
        assert row["plant_contact"] == "(716) 879-5000"
        assert row["plant_head"] == "Ram Ramanujam"
        assert row["plant_head_email"] == "ram.ramanujam@gm.com"
        assert row["plant_head_phone"] == "(716) 879-5000 ext. 101"
        assert row["tech_head"] == "Sarah Connor"
        assert row["tech_head_email"] == "sarah.connor@gm.com"
        assert row["tech_head_phone"] == "(716) 879-5000 ext. 210"
        assert "https://media.gm.com/tonawanda-announcement" in row["source_urls"]

