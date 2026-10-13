"""Unit tests for System 1 Non-Autoregressive Decision Engine (Laya)."""

from unittest.mock import MagicMock, patch
import pytest

from argus.brain.system1 import System1DecisionEngine
from argus.domain.task import ResearchTask
from argus.search.models import SearchResult


@pytest.fixture
def mock_laya_router():
    """Fixture providing a mocked Laya Router for fast unit testing."""
    mock_router = MagicMock()

    def mock_predict(state, questions, **kwargs):
        answers = {}
        if "relevance" in questions or "substantive" in questions:
            # Check keywords in state for deterministic testing
            state_lower = state.lower()
            if any(w in state_lower for w in ["plant", "manager", "assembly", "factory", "director"]):
                answers["relevance"] = {"type": "noul", "noul": 0.88, "confidence": 0.88}
                answers["substantive"] = {"type": "noul", "noul": 0.88, "confidence": 0.88}
                answers["category"] = {"type": "choice", "choice": "factual"}
            else:
                answers["relevance"] = {"type": "noul", "noul": 0.12, "confidence": 0.88}
                answers["substantive"] = {"type": "noul", "noul": 0.10, "confidence": 0.90}
                answers["category"] = {"type": "choice", "choice": "boilerplate"}

        if "archetype" in questions:
            if "permit" in state.lower() or "compliance" in state.lower():
                answers["archetype"] = {"type": "choice", "choice": "regulatory"}
            elif "appointed" in state.lower() or "names" in state.lower():
                answers["archetype"] = {"type": "choice", "choice": "newsroom"}
            else:
                answers["archetype"] = {"type": "choice", "choice": "directory"}

        if "difficulty" in questions:
            if "unlisted" in state.lower() or "obscure" in state.lower():
                answers["difficulty"] = {"type": "score", "score": 2}
            else:
                answers["difficulty"] = {"type": "score", "score": 1}

        if "priority_level" in questions:
            st = state.lower()
            if any(w in st for w in ["boundary", "municipal", "city limit", "township", "county", "postal"]):
                answers["priority_level"] = {"type": "choice", "choice": "deprioritized"}
            elif any(w in st for w in ["director", "manager", "head", "lead", "phone", "email", "contact"]):
                answers["priority_level"] = {"type": "choice", "choice": "urgent"}
            else:
                answers["priority_level"] = {"type": "choice", "choice": "primary"}

        if "scope" in questions:
            st = state.lower()
            if "multi-facility" in st or "plant" in st or "automotive" in st:
                answers["scope"] = {"type": "choice", "choice": "exhaustive"}
            elif "enterprise" in st:
                answers["scope"] = {"type": "choice", "choice": "targeted"}
        if "should_branch_deeper" in questions:
            st = state.lower()
            if any(w in st for w in ["boundary", "municipal", "township", "county", "tax parcel", "postal"]):
                answers["should_branch_deeper"] = {"type": "choice", "choice": "halt_shallow"}
            else:
                answers["should_branch_deeper"] = {"type": "choice", "choice": "allow_deep"}

        return {"model": "laya-rl-agent", "answers": answers}

    mock_router.predict.side_effect = mock_predict
    return mock_router



def test_system1_fallback_when_unavailable():
    """Engine must gracefully fall back to default behavior if Laya fails to load."""
    engine = System1DecisionEngine()
    engine._router = None
    engine._is_available = False

    raw_results = [
        SearchResult(url="https://example.com/1", title="Result 1", snippet="Snippet 1"),
        SearchResult(url="https://example.com/2", title="Result 2", snippet="Snippet 2"),
    ]

    filtered = engine.triage_search_results(
        results=raw_results,
        objective_target="Automotive",
        task_title="Find Plants",
        top_k=2,
    )
    assert len(filtered) == 2
    assert filtered[0].url == "https://example.com/1"

    is_rel, conf, cat = engine.triage_document(
        doc_text="Sample text",
        task_title="Find Plants",
        objective_target="Automotive",
    )
    assert is_rel is True
    assert cat == "unfiltered"


def test_system1_heuristic_discards_errors_even_without_router():
    """When router is None, heuristic must still catch and discard 404s, login walls, and Cloudflare pages."""
    engine = System1DecisionEngine()
    engine._router = None
    engine._is_available = False

    # 404 error
    is_rel, conf, cat = engine.triage_document(
        doc_text="404 Not Found. The resource does not exist on this server.",
        task_title="Find Plants",
        objective_target="Automotive",
    )
    assert is_rel is False
    assert cat == "boilerplate"

    # Cloudflare challenge
    is_rel, conf, cat = engine.triage_document(
        doc_text="Just a moment... Please enable cookies and check your browser before accessing the site.",
        task_title="Find Plants",
        objective_target="Automotive",
    )
    assert is_rel is False
    assert cat == "boilerplate"

    # LinkedIn login wall
    is_rel, conf, cat = engine.triage_document(
        doc_text="Join LinkedIn to view full profile. Sign in to LinkedIn to continue.",
        task_title="Find Plants",
        objective_target="Automotive",
    )
    assert is_rel is False
    assert cat == "boilerplate"


def test_system1_snippet_triage(mock_laya_router):
    """Engine should prioritize relevant snippets over irrelevant noise."""
    engine = System1DecisionEngine()
    engine._router = mock_laya_router
    engine._is_available = True

    results = [
        SearchResult(
            url="https://news.com/recipe",
            title="Best Chocolate Cake Recipe",
            snippet="Bake at 350 degrees with sugar and flour.",
        ),
        SearchResult(
            url="https://press.gm.com/arlington",
            title="GM Arlington Assembly Names New Plant Manager",
            snippet="General Motors announced new plant leadership for the Texas assembly plant.",
        ),
        SearchResult(
            url="https://sports.com/scores",
            title="Yesterday Baseball Highlights",
            snippet="Home run in the ninth inning seals the victory.",
        ),
    ]

    top_results = engine.triage_search_results(
        results=results,
        objective_target="US Automotive",
        task_title="Find Plant Managers",
        top_k=1,
    )

    assert len(top_results) == 1
    assert "arlington" in top_results[0].url


def test_system1_document_triage(mock_laya_router):
    """Engine should flag cookie policies and 404s as boilerplate."""
    engine = System1DecisionEngine()
    engine._router = mock_laya_router
    engine._is_available = True

    # 1. Boilerplate document
    is_rel, conf, cat = engine.triage_document(
        doc_text="404 Page Not Found. Please accept cookies and terms of service to continue.",
        task_title="Identify Kentucky Truck Plant Manager",
        objective_target="Ford Facilities",
    )
    assert is_rel is False
    assert cat == "boilerplate"

    # 2. Substantive document
    is_rel, conf, cat = engine.triage_document(
        doc_text="Ford Kentucky Truck Plant is an active assembly factory employing 9,000 workers under plant manager leadership.",
        task_title="Identify Kentucky Truck Plant Manager",
        objective_target="Ford Facilities",
    )
    assert is_rel is True
    assert cat == "factual"


def test_system1_archetype_routing(mock_laya_router):
    """Engine should classify search archetypes appropriately."""
    engine = System1DecisionEngine()
    engine._router = mock_laya_router
    engine._is_available = True

    archetype_news = engine.classify_search_archetype(
        task_title="Executive Appointments",
        task_description="Ford names new manufacturing vice president",
        objective_target="Automotive",
    )
    assert archetype_news == "newsroom"

    archetype_reg = engine.classify_search_archetype(
        task_title="Environmental Compliance",
        task_description="EPA emissions permit records for assembly site",
        objective_target="Automotive",
    )
    assert archetype_reg == "regulatory"


def test_system1_task_difficulty(mock_laya_router):
    """Engine should scale task budget according to obscurity."""
    engine = System1DecisionEngine()
    engine._router = mock_laya_router
    engine._is_available = True

    budget, crawl = engine.estimate_task_difficulty("Find obscure unlisted plant managers in private firms")
    assert budget >= 15
    assert crawl >= 3


def test_system1_priority_scoring(mock_laya_router):
    """Engine should score urgent leadership tasks as 10 and boundary trivia as 3."""
    engine = System1DecisionEngine()
    engine._router = mock_laya_router
    engine._is_available = True

    # 1. Urgent leadership task
    p_urgent = engine.score_task_priority(
        task_title="Identify Plant Director for Arlington Assembly",
        task_description="Find plant director and executive head",
        objective_goal="Map US auto plants, find plant director and contact info",
        required_fields=["plant_head", "contact_info"],
    )
    assert p_urgent == 10

    # 2. Deprioritized municipal boundary trivia
    p_trivia = engine.score_task_priority(
        task_title="Disambiguate: Verify whether Lansing Delta lies within Delta Township or city limits",
        task_description="Resolve municipal boundary contradiction",
        objective_goal="Map US auto plants, find plant director and contact info",
        required_fields=["plant_head", "contact_info"],
    )
    assert p_trivia == 3


def test_system1_priority_heuristic_fallback():
    """Heuristic fallback should correctly classify without Laya router."""
    engine = System1DecisionEngine()
    engine._router = None
    engine._is_available = False

    p_lead = engine.score_task_priority(
        task_title="Identify Technical Lead for Tonawanda Engine",
        task_description="Find chief engineer",
    )
    assert p_lead == 10

    p_trivia = engine.score_task_priority(
        task_title="Disambiguate: Check county parcel records for municipal boundary",
        task_description="Verify township vs city jurisdiction",
    )
    assert p_trivia == 3


def test_system1_calibrate_budget_and_depth(mock_laya_router):
    """Engine should dynamically calibrate (max_tasks, max_depth) up to 50 tasks and depth 5."""
    engine = System1DecisionEngine()
    engine._router = mock_laya_router
    engine._is_available = True

    tasks, depth = engine.calibrate_budget_and_depth(
        objective_target="US Automotive Industry",
        intelligence_goal="Multi-facility automotive plant investigation across 30 plants",
        required_fields=["manufacturing_plant", "plant_head", "contact_info"],
    )
    assert tasks == 50
    assert depth == 5


def test_system1_should_branch_deeper_laya(mock_laya_router):
    """Laya should allow deep recursion for personnel but halt on municipal boundary trivia."""
    engine = System1DecisionEngine()
    engine._router = mock_laya_router
    engine._is_available = True

    # Critical personnel at depth 3: allow deep (up to 5)
    allow_personnel = engine.should_branch_deeper(
        task_title="Investigate plant director for Tonawanda Engine",
        task_description="Verify current plant manager appointment",
        current_depth=3,
        max_depth=5,
        objective_goal="Identify plant directors",
    )
    assert allow_personnel is True

    # Secondary municipal border at depth 3: halt shallow
    halt_trivia = engine.should_branch_deeper(
        task_title="Disambiguate: Delta Township municipal boundary coordinates",
        task_description="Check tax parcel and city limits",
        current_depth=3,
        max_depth=5,
        objective_goal="Identify plant directors",
    )
    assert halt_trivia is False


def test_system1_should_branch_deeper_heuristic():
    """Heuristic fallback should halt municipal borders at depth >= 2 while allowing personnel."""
    engine = System1DecisionEngine()
    engine._router = None
    engine._is_available = False

    # Depth 1 always allowed for discovery
    assert engine.should_branch_deeper("Disambiguate municipal boundary", current_depth=1) is True

    # Depth >= 2: municipal trivia halted
    assert engine.should_branch_deeper("Disambiguate municipal boundary", current_depth=2) is False

    # Depth 4: plant director allowed
    assert engine.should_branch_deeper("Investigate plant director", current_depth=4, max_depth=5) is True

    # Depth > max_depth: blocked
    assert engine.should_branch_deeper("Investigate plant director", current_depth=6, max_depth=5) is False


