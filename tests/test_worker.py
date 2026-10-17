from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from argus.crawler.models import Document
from argus.domain.claim import ClaimStatus
from argus.domain.entity import Entity
from argus.domain.objective import ResearchObjective
from argus.domain.task import ResearchTask
from argus.llm.mock import MockLLMProvider
from argus.llm.openrouter import OpenRouterLLMProvider
from argus.storage.db import DatabaseManager
from argus.storage.repository import ArgusRepository
from argus.worker.engine import WorkerEngine
from argus.worker.models import (
    ExtractedClaimItem,
    ExtractedEntityItem,
    ExtractionPayload,
    RelevanceAssessment,
)


@pytest.fixture
def repo():
    db = DatabaseManager(":memory:")
    return ArgusRepository(db)


@pytest.fixture
def sample_objective(repo):
    obj = ResearchObjective(
        target="US Automobile Manufacturers",
        target_type="industry",
        intelligence_goal="Identify plants, locations, and key leadership.",
        required_fields=["name", "facility", "location"],
        success_criteria="At least 5 plants verified",
    )
    repo.save_objective(obj)
    return obj


@pytest.fixture
def sample_task(repo, sample_objective):
    task = ResearchTask(
        objective_id=sample_objective.objective_id,
        title="Extract Ford Truck Plants",
        description="Find all Ford heavy truck manufacturing facilities.",
    )
    repo.save_task(task)
    return task


@pytest.mark.asyncio
async def test_mock_llm_provider():
    mock_payload = ExtractionPayload(
        relevance=RelevanceAssessment(
            is_relevant=True, reasoning="Document covers Ford plants"
        ),
        entities=[
            ExtractedEntityItem(
                name="Ford Motor Company",
                entity_type="company",
                aliases=["Ford"],
            )
        ],
    )

    provider = MockLLMProvider(responses=[mock_payload])
    result = await provider.generate_structured(
        prompt="Extract entities",
        response_model=ExtractionPayload,
    )

    assert result.relevance.is_relevant is True
    assert len(result.entities) == 1
    assert result.entities[0].name == "Ford Motor Company"
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_openrouter_provider_json_formatting():
    provider = OpenRouterLLMProvider(
        api_key="test-key",
        model="deepseek/deepseek-chat:free",
    )

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": '```json\n{"is_relevant": true, "reasoning": "Relevant context", "confidence": 0.95}\n```'
                }
            }
        ]
    }

    with patch(
        "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=fake_response
    ):
        result = await provider.generate_structured(
            prompt="Is this relevant?",
            response_model=RelevanceAssessment,
        )
        assert result.is_relevant is True
        assert result.reasoning == "Relevant context"
        assert result.confidence == 0.95


@pytest.mark.asyncio
async def test_worker_handles_irrelevant_document(repo, sample_objective, sample_task):
    doc = Document(
        url="https://recipes.com/pie",
        title="Apple Pie Recipe",
        text_content="Bake at 350 degrees until golden brown.",
    )

    mock_payload = ExtractionPayload(
        relevance=RelevanceAssessment(
            is_relevant=False,
            reasoning="Cooking recipe unrelated to automotive manufacturing.",
        ),
        entities=[],
        claims=[],
    )

    provider = MockLLMProvider(responses=[mock_payload])
    engine = WorkerEngine(repo=repo, llm=provider)

    result = await engine.process_document(doc, sample_task, sample_objective)

    assert result.is_relevant is False
    assert len(result.entities_created) == 0
    assert len(result.claims_created) == 0

    # Ensure event was logged
    events = repo.list_events(sample_objective.objective_id)
    assert len(events) == 1
    assert events[0].payload["status"] == "irrelevant"


@pytest.mark.asyncio
async def test_worker_extracts_entities_and_grounded_claims(
    repo, sample_objective, sample_task
):
    doc_text = (
        "Ford Motor Company operates the Kentucky Truck Plant located in Louisville, Kentucky. "
        "The plant produces the Ford Super Duty truck."
    )
    doc = Document(
        url="https://ford.com/plants/ktp",
        title="Kentucky Truck Plant Overview",
        text_content=doc_text,
    )
    repo.save_document(doc)

    mock_payload = ExtractionPayload(
        relevance=RelevanceAssessment(
            is_relevant=True,
            reasoning="Contains direct facility and production information.",
        ),
        entities=[
            ExtractedEntityItem(
                name="Ford Motor Company",
                entity_type="company",
                aliases=["Ford"],
            ),
            ExtractedEntityItem(
                name="Kentucky Truck Plant",
                entity_type="facility",
                aliases=["KTP"],
                attributes={"city": "Louisville", "state": "Kentucky"},
            ),
        ],
        claims=[
            ExtractedClaimItem(
                subject_name="Ford Motor Company",
                predicate="OPERATES_FACILITY",
                object_value="Kentucky Truck Plant",
                verbatim_passage="Ford Motor Company operates the Kentucky Truck Plant located in Louisville, Kentucky.",
                confidence=0.95,
            )
        ],
        suggested_followup_tasks=["Find plant manager of Kentucky Truck Plant"],
    )

    provider = MockLLMProvider(responses=[mock_payload])
    engine = WorkerEngine(repo=repo, llm=provider)

    result = await engine.process_document(doc, sample_task, sample_objective)

    assert result.is_relevant is True
    assert len(result.entities_created) == 2
    assert len(result.evidence_created) == 1
    assert len(result.claims_created) == 1
    assert len(result.suggested_followup_tasks) == 1

    # Verify Evidence was properly grounded with char offsets and content_hash
    evidence = result.evidence_created[0]
    assert evidence.source_id == doc.content_hash
    assert evidence.url == doc.url
    assert evidence.char_start == 0
    assert evidence.char_end == len(mock_payload.claims[0].verbatim_passage)
    assert doc_text[evidence.char_start : evidence.char_end] == evidence.passage

    # Verify Claim linkage
    claim = result.claims_created[0]
    assert claim.predicate == "OPERATES_FACILITY"
    assert claim.object_value == "Kentucky Truck Plant"
    assert claim.evidence_ids == [evidence.evidence_id]
    assert claim.status == ClaimStatus.PENDING

    # Subject and Object entity IDs should match created entities
    ktp_entity = next(
        e for e in result.entities_created if e.canonical_name == "Kentucky Truck Plant"
    )
    ford_entity = next(
        e for e in result.entities_created if e.canonical_name == "Ford Motor Company"
    )
    assert claim.subject_entity_id == ford_entity.entity_id
    assert claim.object_entity_id == ktp_entity.entity_id

    # Verify database persistence
    stored_claim = repo.get_claim(claim.claim_id)
    assert stored_claim is not None
    assert stored_claim.claim_id == claim.claim_id


@pytest.mark.asyncio
async def test_worker_resolves_existing_entities(repo, sample_objective, sample_task):
    # Pre-populate repository with an existing entity
    existing_entity = Entity(
        canonical_name="Ford Motor Company",
        entity_type="company",
        aliases=["Ford"],
        attributes={"country": "USA"},
        objective_id=sample_objective.objective_id,
    )
    repo.save_entity(existing_entity)

    doc_text = "Ford announced new upgrades to the factory line."
    doc = Document(
        url="https://ford.com/news/update",
        title="Factory Upgrades",
        text_content=doc_text,
    )

    mock_payload = ExtractionPayload(
        relevance=RelevanceAssessment(is_relevant=True, reasoning="Relevant"),
        entities=[
            ExtractedEntityItem(
                name="Ford",  # Alias of existing entity
                entity_type="company",
                aliases=["FoMoCo"],  # New alias
                attributes={"status": "public"},
            )
        ],
        claims=[],
    )

    provider = MockLLMProvider(responses=[mock_payload])
    engine = WorkerEngine(repo=repo, llm=provider)

    result = await engine.process_document(doc, sample_task, sample_objective)

    # Should update existing entity instead of creating a duplicate
    assert len(result.entities_created) == 0
    assert len(result.entities_updated) == 1

    updated_entity = result.entities_updated[0]
    assert updated_entity.entity_id == existing_entity.entity_id
    assert updated_entity.canonical_name == "Ford Motor Company"
    assert "FoMoCo" in updated_entity.aliases
    assert updated_entity.attributes["country"] == "USA"
    assert updated_entity.attributes["status"] == "public"

    # Verify only 1 entity exists in repository
    all_entities = repo.list_entities()
    assert len(all_entities) == 1


@pytest.mark.asyncio
async def test_worker_verbatim_quote_fallback(repo, sample_objective, sample_task):
    doc = Document(
        url="https://ford.com/plants/chicago",
        title="Chicago Plant",
        text_content="General assembly operations happen in Chicago.",
    )

    mock_payload = ExtractionPayload(
        relevance=RelevanceAssessment(is_relevant=True, reasoning="Relevant"),
        entities=[
            ExtractedEntityItem(
                name="Chicago Assembly Plant",
                entity_type="facility",
            )
        ],
        claims=[
            ExtractedClaimItem(
                subject_name="Chicago Assembly Plant",
                predicate="LOCATED_IN",
                object_value="Chicago, Illinois",
                verbatim_passage="This quote was hallucinated and is not verbatim in doc text.",
                confidence=0.7,
            )
        ],
    )

    provider = MockLLMProvider(responses=[mock_payload])
    engine = WorkerEngine(repo=repo, llm=provider)

    result = await engine.process_document(doc, sample_task, sample_objective)

    assert result.is_relevant is True
    assert len(result.evidence_created) == 1
    evidence = result.evidence_created[0]
    # Char offsets should gracefully be None when quote is not a direct substring
    assert evidence.char_start is None
    assert evidence.char_end is None


@pytest.mark.asyncio
async def test_mock_llm_provider_raises_on_unconfigured():
    provider = MockLLMProvider(responses=[])
    with pytest.raises(ValueError, match="no configured response"):
        await provider.generate_structured(
            prompt="Test",
            response_model=RelevanceAssessment,
        )


@pytest.mark.asyncio
async def test_worker_prevents_merging_on_generic_shared_aliases_and_different_types(
    repo, sample_objective, sample_task
):
    """Bug 1.4 Regression Test:

    Verify that generic shared aliases (e.g. 'company', 'automaker') and mismatched
    entity types do NOT cause unrelated entities to merge into a single node.
    """
    # Pre-populate Ford Motor Company
    existing_entity = Entity(
        canonical_name="Ford Motor Company",
        entity_type="company",
        aliases=["Ford", "Company", "Automaker"],
        objective_id=sample_objective.objective_id,
    )
    repo.save_entity(existing_entity)

    doc = Document(
        url="https://industry-news.com/overview",
        title="Automotive Overview",
        text_content="GM and Ford are competing automakers. John Ford is a supervisor.",
    )

    mock_payload = ExtractionPayload(
        relevance=RelevanceAssessment(is_relevant=True, reasoning="Relevant"),
        entities=[
            # Entity 1: Unrelated company sharing generic aliases "Company", "Automaker"
            ExtractedEntityItem(
                name="General Motors",
                entity_type="company",
                aliases=["GM", "Company", "Automaker"],
            ),
            # Entity 2: Different entity type (person) with name matching company alias
            ExtractedEntityItem(
                name="John Ford",
                entity_type="person",
                aliases=["Ford"],
            ),
            # Entity 3: Legitimate company match for Ford Motor Company
            ExtractedEntityItem(
                name="Ford",
                entity_type="company",
                aliases=["FoMoCo"],
            ),
        ],
        claims=[],
    )

    provider = MockLLMProvider(responses=[mock_payload])
    engine = WorkerEngine(repo=repo, llm=provider)

    result = await engine.process_document(doc, sample_task, sample_objective)

    # General Motors and John Ford must be newly created (NOT merged into Ford Motor Company)
    created_names = {e.canonical_name for e in result.entities_created}
    assert "General Motors" in created_names
    assert "John Ford" in created_names
    assert len(result.entities_created) == 2

    # Ford must be resolved and updated into Ford Motor Company
    assert len(result.entities_updated) == 1
    assert result.entities_updated[0].canonical_name == "Ford Motor Company"
    assert "FoMoCo" in result.entities_updated[0].aliases

    # Repository must hold 3 separate entities
    all_entities = repo.list_entities(objective_id=sample_objective.objective_id)
    assert len(all_entities) == 3


def test_worker_find_passage_offsets_newline_and_whitespace_resilient(repo):
    """Bug 5.1 Regression Test:

    Verify that verbatim passage offset extraction is resilient to Windows CRLF vs Unix LF
    newline variations and whitespace normalization, preserving character offsets in the original text.
    """
    engine = WorkerEngine(repo=repo, llm=MockLLMProvider([]))

    # Text containing Windows CRLF newlines and extra spacing
    doc_text = (
        "Facility Report 2026.\r\n"
        "Kentucky Truck Plant\r\n"
        "builds F-Series Super Duty trucks in Louisville.\r\n"
        "Plant Manager: Jane Smith."
    )

    # Passage with normalized Unix LF newlines and single spaces as output by LLMs
    normalized_passage = (
        "Kentucky Truck Plant\nbuilds F-Series Super Duty trucks in Louisville."
    )

    start, end = engine._find_passage_offsets(doc_text, normalized_passage)
    assert start is not None
    assert end is not None
    # Matched substring in original text
    matched_text = doc_text[start:end]
    assert "Kentucky Truck Plant" in matched_text
    assert "Louisville." in matched_text
    assert start == doc_text.find("Kentucky Truck Plant")


@pytest.mark.asyncio
async def test_openrouter_provider_handles_conversational_prelude_and_thinking():
    """Bug 5.2 Regression Test:

    Verify that OpenRouterLLMProvider robustly extracts valid JSON payloads even when
    models return conversational preludes, thinking blocks, or trailing commentary.
    """
    provider = OpenRouterLLMProvider(api_key="test-key", model="test/model:free")

    # Case 1: Conversational prelude + markdown code fence + trailing greeting
    prelude_content = (
        "Certainly! Here is the extracted JSON analysis for the facility:\n\n"
        "```json\n"
        '{"is_relevant": true, "reasoning": "Direct evidence found", "confidence": 0.98}\n'
        "```\n\n"
        "Let me know if you would like me to extract more details!"
    )

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "choices": [{"message": {"content": prelude_content}}]
    }

    with patch(
        "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=fake_response
    ):
        result = await provider.generate_structured(
            prompt="Analyze document",
            response_model=RelevanceAssessment,
        )
        assert result.is_relevant is True
        assert result.reasoning == "Direct evidence found"
        assert result.confidence == 0.98

    # Case 2: Thinking process without markdown code fence
    thinking_content = (
        "Thinking Process:\n"
        "1. Checked facility location.\n"
        "2. Verified plant manager.\n\n"
        '{"is_relevant": true, "reasoning": "Verified data", "confidence": 0.90}'
    )

    fake_response.json.return_value = {
        "choices": [{"message": {"content": thinking_content}}]
    }

    with patch(
        "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=fake_response
    ):
        result2 = await provider.generate_structured(
            prompt="Analyze document",
            response_model=RelevanceAssessment,
        )
        assert result2.is_relevant is True
        assert result2.confidence == 0.90

