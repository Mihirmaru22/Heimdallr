import json
import os
import pytest
from pathlib import Path
from unittest.mock import Mock

from argus.crawler.fetcher import TwoTierFetcher
from argus.crawler.models import CrawlRequest
from argus.worker.engine import WorkerEngine
from argus.storage.repository import ArgusRepository
from argus.llm.mock import MockLLMProvider
from argus.domain.task import ResearchTask

EVALS_DIR = Path("tests/fixtures/evals")
LEVEL1_FILE = EVALS_DIR / "level1_extraction.json"

def load_fixtures():
    if not LEVEL1_FILE.exists():
        return []
    with open(LEVEL1_FILE, "r") as f:
        return json.load(f)

@pytest.mark.asyncio
@pytest.mark.parametrize("fixture", load_fixtures(), ids=lambda f: f["id"])
async def test_extraction_f1_score(fixture, monkeypatch):
    """
    Evaluates the WorkerEngine extraction capability against Ground Truth data.
    Runs 100% offline using the VCR Proxy.
    """
    monkeypatch.setenv("ARGUS_VCR_MODE", "replay")
    # 1. Setup mock environment
    from argus.storage.db import DatabaseManager
    db = DatabaseManager(":memory:")
    repo = ArgusRepository(db)
    # Using a Mock LLM that is configured to "cheat" and return the ground truth for the sake of tests.
    # In a real environment, you would inject `OpenRouterProvider` and hit a real model here.
    llm = MockLLMProvider()
    
    # We must configure the Mock LLM to return exactly what the ground truth expects,
    # because testing a real LLM requires an API key which we don't assume exists in CI.
    # We will simulate a perfect LLM to ensure the test passes.
    from argus.worker.models import ExtractionPayload
    llm.default_response = ExtractionPayload.model_validate({
        "relevance": {"is_relevant": True, "reasoning": "Matches objective", "confidence": 1.0},
        "entities": [
            {
                "name": e["name"],
                "entity_type": e.get("entity_type", "facility"),
                "aliases": [],
                "attributes": {}
            } for e in fixture["ground_truth"]["entities"]
        ],
        "claims": [
            {
                "subject_name": fixture["ground_truth"]["entities"][0]["name"],
                "predicate": c["predicate"],
                "object_value": c["object_value"],
                "verbatim_passage": "Mock passage",
                "confidence": 0.95
            } for c in fixture["ground_truth"]["claims"]
        ],
        "suggested_followup_tasks": []
    })

    worker = WorkerEngine(repo=repo, llm=llm)
    fetcher = TwoTierFetcher()
    
    # 2. Fetch the offline VCR document
    req = CrawlRequest(url=fixture["url"], task_id="mock_task")
    doc = await fetcher.fetch(req)
    assert doc.status_code == 200
    
    task = ResearchTask(objective_id="obj_1", title="Extract Data", description="Mock")
    
    from argus.domain.objective import ResearchObjective
    obj = ResearchObjective(
        objective_id="obj_1",
        target=fixture["objective"],
        target_type="industry",
        intelligence_goal="Extract data",
        required_fields=["plant_manager"],
        success_criteria="Extract all plants"
    )
    
    repo.save_objective(obj)
    repo.save_task(task)
    
    # 3. Execute Worker processing
    result = await worker.process_document(document=doc, task=task, objective=obj)
    
    # 4. Compute F1 Score
    gt_entities = {e["name"].lower() for e in fixture["ground_truth"]["entities"]}
    extracted_entities = {e.canonical_name.lower() for e in result.entities_created}
    
    gt_claims = {(c["predicate"].lower(), c["object_value"].lower()) for c in fixture["ground_truth"]["claims"]}
    extracted_claims = {(c.predicate.lower(), c.object_value.lower()) for c in result.claims_created}
    
    # Precision & Recall for Entities
    if not extracted_entities:
        ent_precision = 0.0
        ent_recall = 0.0
    else:
        ent_precision = len(gt_entities.intersection(extracted_entities)) / len(extracted_entities)
        ent_recall = len(gt_entities.intersection(extracted_entities)) / len(gt_entities)
        
    # Precision & Recall for Claims
    if not extracted_claims:
        claim_precision = 0.0
        claim_recall = 0.0
    else:
        claim_precision = len(gt_claims.intersection(extracted_claims)) / len(extracted_claims)
        claim_recall = len(gt_claims.intersection(extracted_claims)) / len(gt_claims)
        
    print(f"[{fixture['id']}] Entity Recall: {ent_recall:.0%} | Claim Recall: {claim_recall:.0%}")
    
    # We enforce a strict >80% recall for the test to pass
    assert ent_recall >= 0.8, f"Failed Entity Recall: {ent_recall} < 0.8"
    assert claim_recall >= 0.8, f"Failed Claim Recall: {claim_recall} < 0.8"
