"""Automated Tests for Milestone P0.3-G: Generalization Validation V2.

Verifies:
1. Benchmark Dataset Integrity & Versioning (100 tasks, 8 categories)
2. Holdout Partition Isolation & No Expected-Answer Leakage
3. Adversarial Entity Resolution Suite (11 boundary cases)
4. Decoupled Evaluator Metrics & Wilson Score Confidence Intervals
5. 18-Class Failure Taxonomy Classifications
"""

import math
from pathlib import Path
import pytest

from argus.investigation.benchmark.v2.adversarial import (
    build_adversarial_entity_suite,
    evaluate_adversarial_case,
)
from argus.investigation.benchmark.v2.corpus import (
    InvestigationCorpusRegistryV2,
    build_generalization_v2_corpus,
)
from argus.investigation.benchmark.v2.evaluator import (
    FailureTaxonomy,
    compute_wilson_ci,
    metric_record,
)
from argus.investigation.benchmark.v2.manifest import (
    build_v2_manifest,
    verify_benchmark_isolation,
)
from argus.investigation.benchmark.v2.tasks import (
    build_generalization_v2_tasks,
)


def test_generalization_v2_task_distribution():
    """Verify exact count of 100 tasks across all 8 required categories."""
    tasks = build_generalization_v2_tasks()
    assert len(tasks) == 100, f"Expected 100 tasks, got {len(tasks)}"

    task_ids = [t.task_id for t in tasks]
    assert len(set(task_ids)) == 100, "Task IDs must be globally unique"

    # Verify category counts
    cat_a = [t for t in tasks if t.task_id.startswith("gen2_task_0") or t.task_id.startswith("gen2_task_1") and int(t.task_id.split("_")[2]) <= 15]
    assert len(cat_a) == 15, f"Category A should have 15 tasks, got {len(cat_a)}"

    cat_b = [t for t in tasks if 16 <= int(t.task_id.split("_")[2]) <= 30]
    assert len(cat_b) == 15, f"Category B should have 15 tasks, got {len(cat_b)}"

    cat_c = [t for t in tasks if 31 <= int(t.task_id.split("_")[2]) <= 45]
    assert len(cat_c) == 15, f"Category C should have 15 tasks, got {len(cat_c)}"

    cat_d = [t for t in tasks if 46 <= int(t.task_id.split("_")[2]) <= 60]
    assert len(cat_d) == 15, f"Category D should have 15 tasks, got {len(cat_d)}"

    cat_e = [t for t in tasks if 61 <= int(t.task_id.split("_")[2]) <= 75]
    assert len(cat_e) == 15, f"Category E should have 15 tasks, got {len(cat_e)}"

    cat_f = [t for t in tasks if 76 <= int(t.task_id.split("_")[2]) <= 85]
    assert len(cat_f) == 10, f"Category F should have 10 tasks, got {len(cat_f)}"

    cat_g = [t for t in tasks if 86 <= int(t.task_id.split("_")[2]) <= 95]
    assert len(cat_g) == 10, f"Category G should have 10 tasks, got {len(cat_g)}"

    cat_h = [t for t in tasks if 96 <= int(t.task_id.split("_")[2]) <= 100]
    assert len(cat_h) == 5, f"Category H should have 5 tasks, got {len(cat_h)}"


def test_generalization_v2_manifest_and_holdout_isolation():
    """Verify manifest version 2.0.0, 20 val / 80 holdout split, and isolation scan."""
    manifest = build_v2_manifest()
    assert manifest.version == "2.0.0"
    assert manifest.total_tasks == 100
    assert manifest.validation_partition.task_count == 20
    assert manifest.holdout_partition.task_count == 80
    assert len(manifest.validation_partition.integrity_hash) == 64
    assert len(manifest.holdout_partition.integrity_hash) == 64

    # Run static isolation scan
    iso_result = verify_benchmark_isolation()
    assert iso_result["status"] == "PASSED"
    assert iso_result["isolation_verified"] is True
    assert len(iso_result["violations"]) == 0


def test_adversarial_entity_resolution_suite():
    """Verify all 11 adversarial entity resolution test cases pass."""
    suite = build_adversarial_entity_suite()
    assert len(suite) == 11

    for case in suite:
        res = evaluate_adversarial_case(case)
        assert res["passed"] is True, f"Failed case {case.test_id} ({case.scenario_type})"


def test_corpus_registry_search_and_discoverability():
    """Verify V2 synthetic corpus has discoverable entities and exact search matching."""
    corpus = build_generalization_v2_corpus()
    assert len(corpus) >= 100

    reg = InvestigationCorpusRegistryV2(docs=corpus)
    entities = reg.get_discoverable_entities()
    assert len(entities) > 50

    # Search for an unseen entity
    res = reg.search("Kuka Dynamics Titan-6 Arm", limit=3)
    assert len(res) > 0
    assert any("Kuka Dynamics" in d.title for d in res)


def test_wilson_confidence_intervals():
    """Verify Wilson score 95% confidence interval computation."""
    low, high = compute_wilson_ci(100, 100)
    assert 0.95 <= low <= 1.0
    assert high == 1.0

    low, high = compute_wilson_ci(0, 100)
    assert low == 0.0
    assert 0.0 <= high <= 0.05

    rec = metric_record(85, 100)
    assert rec["numerator"] == 85
    assert rec["denominator"] == 100
    assert rec["percentage"] == 85.0
    assert rec["ci_95"][0] < 85.0 < rec["ci_95"][1]


def test_failure_taxonomy_constants():
    """Verify that all 18 failure classes are defined and accessible."""
    expected_classes = [
        "ENTITY_RESOLUTION_FAILURE",
        "RETRIEVAL_FAILURE",
        "RELEVANT_EVIDENCE_MISSED",
        "INCORRECT_EVIDENCE_ATTRIBUTION",
        "UNSUPPORTED_CLAIM",
        "CONTRADICTION_MISSED",
        "FALSE_CONTRADICTION",
        "TEMPORAL_CONFUSION",
        "PARENT_SUBSIDIARY_CONTAMINATION",
        "INCORRECT_NOT_FOUND",
        "INCORRECT_INSUFFICIENT_EVIDENCE",
        "PREMATURE_STOPPING",
        "UNNECESSARY_CONTINUED_RESEARCH",
        "MULTI_HOP_REASONING_FAILURE",
        "SOURCE_DUPLICATION_MISTAKEN_FOR_CORROBORATION",
        "INCORRECT_ANSWER_SYNTHESIS",
        "EVALUATION_AMBIGUITY",
        "SECURITY_REJECTION_OR_SAFE_RETRIEVAL_FAILURE",
    ]
    for c in expected_classes:
        assert hasattr(FailureTaxonomy, c), f"Missing taxonomy class {c}"
