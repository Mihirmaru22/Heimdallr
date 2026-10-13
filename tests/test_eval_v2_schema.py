"""Tests for Eval V2 task schema validation, benchmark loading, and versioning."""

import json
from pathlib import Path
import pytest
from argus.evals.v2.models import (
    BenchmarkCategory,
    BenchmarkSplit,
    DifficultyTier,
    EvalV2Task,
    SpecialistType,
    StopReason,
)
from argus.evals.v2.holdout import BenchmarkSplitManager


def test_eval_v2_task_schema_validation():
    """Verify task validation and constraints."""
    data = {
        "task_id": "test_v2_001",
        "title": "Test Task",
        "query": "Who is the CEO of AeroDynamics Corp?",
        "category": BenchmarkCategory.LEADERSHIP_INTELLIGENCE.value,
        "difficulty_tier": DifficultyTier.TIER_1_HARD.value,
        "split": BenchmarkSplit.FROZEN_REGRESSION.value,
        "known_context": {"country": "US"},
        "expected_output": {
            "expected_entities": ["AeroDynamics Corp", "Arthur Sterling"],
            "expected_relationships": [{"subject": "AeroDynamics Corp", "predicate": "officer", "object": "Arthur Sterling"}],
            "expected_epistemic_status": "SUPPORTED",
            "expected_stop_reason": StopReason.OBJECTIVE_SATISFIED.value,
            "required_specialists": [SpecialistType.CORPORATE.value],
        },
        "metadata": {"version": "2.0"},
    }
    task = EvalV2Task.model_validate(data)
    assert task.task_id == "test_v2_001"
    assert task.difficulty_tier == DifficultyTier.TIER_1_HARD
    assert task.category == BenchmarkCategory.LEADERSHIP_INTELLIGENCE
    assert task.expected_output.expected_entities == ["AeroDynamics Corp", "Arthur Sterling"]


def test_eval_v2_benchmark_tasks_file_loading():
    """Verify full frozen benchmark file loads cleanly and contains required scale."""
    split_mgr = BenchmarkSplitManager()
    tasks = split_mgr.all_tasks

    assert len(tasks) >= 100, f"Expected at least 100 tasks, got {len(tasks)}"
    assert len(tasks) <= 150, f"Expected at most 150 tasks, got {len(tasks)}"

    # Check category distribution
    categories = {t.category for t in tasks}
    assert len(categories) == 25, f"Expected all 25 categories, got {len(categories)}"

    # Check difficulty tiers presence
    tiers = {t.difficulty_tier for t in tasks}
    assert tiers == {
        DifficultyTier.TIER_1_HARD,
        DifficultyTier.TIER_2_VERY_HARD,
        DifficultyTier.TIER_3_EXTREME,
        DifficultyTier.TIER_4_ADVERSARIAL,
    }


def test_eval_v2_versioning_and_metadata():
    """Verify versioning metadata in benchmark file."""
    path = Path("/data/shared/project/PlayGround/Argus/data/evals/v2/benchmark_tasks.json")
    assert path.exists()
    with open(path) as f:
        doc = json.load(f)
    assert doc["benchmark_name"] == "heimdallr_eval_v2"
    assert doc["version"] == "2.0"
    assert doc["task_count"] == len(doc["tasks"])
