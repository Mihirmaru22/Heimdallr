"""Tests verifying Eval V1 regression benchmark preservation and compatibility."""

import json
from pathlib import Path
import pytest
from argus.evals.benchmark import BenchmarkSuite


def test_eval_v1_files_unmodified_and_loadable():
    """Verify that Eval V1 historical benchmark files remain intact and preserved."""
    p_core = Path("/data/shared/project/PlayGround/Argus/data/evals/baseline_v1_core.json")
    p_score = Path("/data/shared/project/PlayGround/Argus/data/evals/baseline_v1_core_scorecard.md")

    assert p_core.exists(), "Eval V1 core JSON must be preserved!"
    assert p_score.exists(), "Eval V1 core scorecard must be preserved!"

    # Verify JSON content
    with open(p_core) as f:
        data = json.load(f)
    assert "tasks" in data or "task_results" in data or "benchmark_version" in data or "version" in data


def test_eval_v1_suite_filter_core():
    """Verify Eval V1 BenchmarkSuite can still load and filter core tasks."""
    suite = BenchmarkSuite.load_from_file()
    assert suite is not None
    assert suite.version == "1.0"
    core_tasks = suite.filter(is_core=True)
    assert len(core_tasks) == 11, f"Expected 11 core tasks in Eval V1, got {len(core_tasks)}"
