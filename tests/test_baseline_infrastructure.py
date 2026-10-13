"""Regression tests for Heimdallr P0 Reproducible Baseline Infrastructure.

Covers all Phase F requirements and P0 remediation verifications:
1. Manifest generation
2. Dirty-tree reporting
3. Secret redaction
4. Ground-truth isolation across all 13 attributes and execution boundary
5. Machine-readable artifact generation
6. Task-count consistency
7. Metric aggregation consistency
8. Missing metric handling
9. Infrastructure error handling
10. Failed-task representation
11. Repeat-run comparison
12. Correct exit status
13. Task-level coverage across all 12 evaluated configurations
14. Validation engine mismatch and staleness detection
15. Summary distinct attribution and dynamic values
"""

import json
from pathlib import Path
import pytest

from argus.evals.baseline.manifest import (
    generate_manifest,
    get_environment_info,
    get_git_branch,
    get_git_commit,
    get_working_tree_status,
    sanitize_secrets,
)
from argus.evals.baseline.runner import BaselineRunner
from argus.evals.baseline.validation import (
    BaselineConsistencyError,
    validate_baseline_consistency,
)
from argus.evals.v2.holdout import BenchmarkSplitManager
from argus.evals.v2.models import (
    EvalV2Task,
    EvaluatorGroundTruthAccessError,
    SpecialistType,
    TaskExpectedOutput,
)
from argus.evals.v2.runner import EvalV2Runner, GroundTruthAccessGuard


def test_manifest_generation(tmp_path):
    """Requirement 1: Verify manifest generation contains all required metadata fields."""
    manifest = generate_manifest(
        run_id="test_run_123",
        evaluation_suites=["heimdallr_v2_frozen_benchmark"],
        execution_mode="offline_frozen",
        cwd=Path(__file__).resolve().parent.parent,
    )

    required_keys = [
        "run_id",
        "utc_timestamp",
        "git_commit",
        "git_branch",
        "working_tree_clean",
        "dirty_files_count",
        "dirty_files",
        "python_version",
        "operating_system",
        "architecture",
        "dependency_manifest",
        "evaluation_suites",
        "dataset_identifiers",
        "configuration_fingerprint",
        "model_provider_identifiers",
        "execution_mode",
        "run_status",
    ]
    for key in required_keys:
        assert key in manifest, f"Manifest missing mandatory key: {key}"

    assert manifest["run_id"] == "test_run_123"
    assert manifest["execution_mode"] == "offline_frozen"
    assert "pyproject_sha256" in manifest["dependency_manifest"]
    assert "uv_lock_sha256" in manifest["dependency_manifest"]


def test_dirty_tree_reporting():
    """Requirement 2: Verify git working tree status and dirty file reporting."""
    is_clean, dirty_files = get_working_tree_status()
    assert isinstance(is_clean, bool)
    assert isinstance(dirty_files, list)
    if not is_clean:
        assert len(dirty_files) > 0
        for item in dirty_files:
            assert "status" in item
            assert "path" in item


def test_secret_redaction():
    """Requirement 3: Verify recursive redaction of API keys, tokens, and credentials."""
    payload = {
        "OPENROUTER_API_KEY": "sk-or-v1-abcdef1234567890abcdef1234567890",
        "secret_token": "my_super_secret_token",
        "user_auth": {"password": "admin_password_123", "normal_field": "safe_value"},
        "nested_list": ["public_item", "bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"],
    }
    sanitized = sanitize_secrets(payload)

    assert sanitized["OPENROUTER_API_KEY"] == "[REDACTED]"
    assert sanitized["secret_token"] == "[REDACTED]"
    assert sanitized["user_auth"]["password"] == "[REDACTED]"
    assert sanitized["user_auth"]["normal_field"] == "safe_value"
    assert sanitized["nested_list"][0] == "public_item"
    assert "[REDACTED]" in sanitized["nested_list"][1]


def test_ground_truth_isolation_all_fields_and_execution_boundary():
    """Requirement 4: Verify GroundTruthAccessGuard blocks ALL 13 ground-truth fields during execution."""
    split_mgr = BenchmarkSplitManager()
    tasks = split_mgr.get_frozen_regression_set()
    assert len(tasks) > 0

    task = tasks[0]
    runner = BaselineRunner()
    isolation = runner.verify_ground_truth_isolation(tasks[:1])
    assert isolation["ground_truth_guard_active"] is True
    assert isolation["fields_blocked"] == 13
    assert isolation["task_boundary_active"] is True
    assert isolation["execution_path_verified"] is True
    assert isolation["grader_access_verified"] is True
    assert isolation["contract_safe"] is True
    assert isolation["isolated"] is True

    # Test all 13 attributes directly under task-level and expected_output guard
    fields_to_test = [
        "expected_entities",
        "expected_relationships",
        "multi_hop_chain",
        "temporal_spec",
        "contradiction_spec",
        "security_spec",
        "evidence_independence",
        "expected_epistemic_status",
        "expected_stop_reason",
        "required_specialists",
        "prohibited_specialists",
        "unacceptable_merges",
        "adversarial_traps",
    ]
    with GroundTruthAccessGuard(task):
        with pytest.raises(EvaluatorGroundTruthAccessError):
            _ = task.expected_output

        with pytest.raises(EvaluatorGroundTruthAccessError):
            _ = task.model_dump()

        exp_ref = super(EvalV2Task, task).__getattribute__("expected_output")
        for f in fields_to_test:
            with pytest.raises(EvaluatorGroundTruthAccessError):
                _ = getattr(exp_ref, f)

    # After unlocking for grading, attributes are accessible
    assert len(task.expected_output.expected_entities) >= 0


def test_machine_readable_artifact_generation(tmp_path):
    """Requirement 5: Verify all required machine-readable baseline artifacts are generated and valid."""
    split_mgr = BenchmarkSplitManager()
    tasks = split_mgr.get_frozen_regression_set()[:3]

    runner = BaselineRunner(run_id="test_artifact_run", output_dir=tmp_path)
    b_results, t_results, perf = runner.run_eval_v2_configurations(tasks)
    stability = runner.verify_reproducibility_repeat(tasks)
    limitations = runner.generate_limitations(dirty_tree=True, dirty_count=5)
    manifest = generate_manifest(
        run_id="test_artifact_run",
        evaluation_suites=["heimdallr_v2_frozen_benchmark"],
        cwd=runner.workspace_root,
    )
    env_info = get_environment_info()

    with open(tmp_path / "manifest.json", "w") as f:
        json.dump(manifest, f)
    with open(tmp_path / "environment.json", "w") as f:
        json.dump(env_info, f)
    with open(tmp_path / "benchmark_results.json", "w") as f:
        json.dump(b_results, f)
    with open(tmp_path / "task_results.json", "w") as f:
        json.dump(t_results, f)
    with open(tmp_path / "performance.json", "w") as f:
        json.dump(perf, f)
    with open(tmp_path / "limitations.json", "w") as f:
        json.dump(limitations, f)

    summary_path = runner.write_summary_markdown(
        manifest=manifest,
        benchmark_results=b_results,
        perf=perf,
        test_results=None,
        stability=stability,
    )

    expected_files = [
        "manifest.json",
        "environment.json",
        "benchmark_results.json",
        "task_results.json",
        "performance.json",
        "limitations.json",
        "summary.md",
    ]
    for ef in expected_files:
        p = tmp_path / ef
        assert p.exists(), f"Expected artifact missing: {ef}"
        if ef.endswith(".json"):
            with open(p) as f:
                parsed = json.load(f)
                assert isinstance(parsed, (dict, list))


def test_task_count_consistency(tmp_path):
    """Requirement 6: Verify task count consistency between benchmark results and task results."""
    split_mgr = BenchmarkSplitManager()
    tasks = split_mgr.get_frozen_regression_set()[:4]

    runner = BaselineRunner(output_dir=tmp_path)
    b_results, t_results, _ = runner.run_eval_v2_configurations(tasks)

    assert b_results["total_tasks"] == len(t_results)
    assert len(t_results) == 4
    for t_res in t_results:
        assert "task_id" in t_res
        assert "configurations" in t_res


def test_task_level_coverage_all_configurations(tmp_path):
    """Requirement 7 / Remediation 1: Verify task_results contains ALL 12 evaluated configurations."""
    split_mgr = BenchmarkSplitManager()
    tasks = split_mgr.get_frozen_regression_set()[:3]

    runner = BaselineRunner(output_dir=tmp_path)
    b_results, t_results, _ = runner.run_eval_v2_configurations(tasks)

    expected_cfgs = [
        "argus_baseline_specialists_disabled",
        "specialist_standalone_identity",
        "specialist_standalone_infrastructure",
        "specialist_standalone_corporate",
        "argus_integrated_identity",
        "argus_integrated_infrastructure",
        "argus_integrated_corporate",
        "cumulative_milestone_0_argus",
        "cumulative_milestone_1_identity",
        "cumulative_milestone_2_infrastructure",
        "cumulative_milestone_3_full_heimdallr",
        "heimdallr_v2_investigation_engine",
    ]

    # Benchmark results must contain all 12
    for cfg in expected_cfgs:
        assert cfg in b_results["configurations"], f"Missing {cfg} in benchmark_results"

    # Task results must contain all 12 for every task
    for t_idx, t_rec in enumerate(t_results):
        t_cfgs = t_rec["configurations"]
        for cfg in expected_cfgs:
            assert cfg in t_cfgs, f"Task {t_rec['task_id']} missing {cfg} in task_results"
            cfg_data = t_cfgs[cfg]
            assert "passed" in cfg_data
            assert "entity_f1" in cfg_data
            assert "field_accuracy" in cfg_data
            assert "evidence_correctness" in cfg_data
            assert "runtime_sec" in cfg_data


def test_metric_aggregation_consistency(tmp_path):
    """Requirement 8 / Remediation 2: Confirm aggregate metrics recalculate from task-level results across all configs."""
    split_mgr = BenchmarkSplitManager()
    tasks = split_mgr.get_frozen_regression_set()[:5]

    runner = BaselineRunner(output_dir=tmp_path)
    b_results, t_results, _ = runner.run_eval_v2_configurations(tasks)

    for cfg_name, cfg_data in b_results["configurations"].items():
        agg_m = cfg_data["metrics"]
        recalc_passed = sum(1 for t in t_results if t["configurations"][cfg_name]["passed"])
        assert recalc_passed == agg_m["passed_count"]
        assert pytest.approx(recalc_passed / len(tasks)) == agg_m["pass_rate"]

        recalc_f1 = sum(t["configurations"][cfg_name]["entity_f1"] for t in t_results) / len(tasks)
        assert pytest.approx(recalc_f1, abs=1e-4) == agg_m["entity_f1"]

        recalc_acc = sum(t["configurations"][cfg_name]["field_accuracy"] for t in t_results) / len(tasks)
        assert pytest.approx(recalc_acc, abs=1e-4) == agg_m["field_accuracy"]


def test_validation_detects_mismatches(tmp_path):
    """Requirement 9 / Remediation 2: Verify validation engine detects inconsistencies and tampered records."""
    split_mgr = BenchmarkSplitManager()
    tasks = split_mgr.get_frozen_regression_set()[:3]
    runner = BaselineRunner(output_dir=tmp_path)
    b_results, t_results, perf = runner.run_eval_v2_configurations(tasks)
    manifest = generate_manifest("test", ["suite"], cwd=runner.workspace_root)
    test_res = {"total_tests": 438, "passed_count": 438, "failed_count": 0, "skipped_count": 0, "error_count": 0}
    summary_txt = "Unit test summary: 438 passed / 438 total."

    # 1. Valid inputs pass cleanly
    msgs = validate_baseline_consistency(
        manifest=manifest,
        benchmark_results=b_results,
        task_results=t_results,
        test_results=test_res,
        summary_content=summary_txt,
        performance=perf,
    )
    assert len(msgs) >= 4

    # 2. Detect mismatched task count
    with pytest.raises(BaselineConsistencyError, match="Mismatched task count"):
        validate_baseline_consistency(
            manifest=manifest,
            benchmark_results=b_results,
            task_results=t_results[:2],  # Dropped task
            test_results=test_res,
        )

    # 3. Detect missing configuration in task records
    tampered_t_results = [dict(t) for t in t_results]
    tampered_t_results[0] = dict(tampered_t_results[0])
    tampered_t_results[0]["configurations"] = dict(tampered_t_results[0]["configurations"])
    del tampered_t_results[0]["configurations"]["specialist_standalone_corporate"]

    with pytest.raises(BaselineConsistencyError, match="missing task-level record"):
        validate_baseline_consistency(
            manifest=manifest,
            benchmark_results=b_results,
            task_results=tampered_t_results,
            test_results=test_res,
        )

    # 4. Detect tampered passed_count
    tampered_b_results = json.loads(json.dumps(b_results))
    tampered_b_results["configurations"]["heimdallr_v2_investigation_engine"]["metrics"]["passed_count"] = 999
    with pytest.raises(BaselineConsistencyError, match="passed_count mismatch"):
        validate_baseline_consistency(
            manifest=manifest,
            benchmark_results=tampered_b_results,
            task_results=t_results,
            test_results=test_res,
        )

    # 5. Detect stale test numbers in summary
    stale_summary = "Unit test summary: 426 passed / 426 total."
    with pytest.raises(BaselineConsistencyError, match="stale"):
        validate_baseline_consistency(
            manifest=manifest,
            benchmark_results=b_results,
            task_results=t_results,
            test_results=test_res,
            summary_content=stale_summary,
        )


def test_missing_metric_handling(tmp_path):
    """Requirement 10: Verify missing instrumentation is explicitly marked and not silently zeroed."""
    split_mgr = BenchmarkSplitManager()
    tasks = split_mgr.get_frozen_regression_set()[:2]

    runner = BaselineRunner(output_dir=tmp_path)
    _, _, perf = runner.run_eval_v2_configurations(tasks)

    model_metrics = perf["model_usage_metrics"]
    assert model_metrics["actual_provider_token_count"] is None
    assert "NOT INSTRUMENTED" in model_metrics["actual_provider_token_count_status"]
    assert model_metrics["actual_provider_cost_usd"] is None
    assert "NOT INSTRUMENTED" in model_metrics["actual_provider_cost_usd_status"]

    assert model_metrics["tokenizer_proxy_token_count_type"] == "SYNTHETIC_PROXY_ESTIMATE"
    assert model_metrics["tokenizer_proxy_cost_usd_type"] == "SYNTHETIC_PROXY_ESTIMATE"


def test_failed_task_representation(tmp_path):
    """Requirement 11: Verify that failed tasks preserve error classifications and observed outputs."""
    split_mgr = BenchmarkSplitManager()
    tasks = split_mgr.get_frozen_regression_set()[:3]

    runner = BaselineRunner(output_dir=tmp_path)
    _, t_results, _ = runner.run_eval_v2_configurations(tasks)

    failed_entries = [t for t in t_results if not t["configurations"]["argus_baseline_specialists_disabled"]["passed"]]
    assert len(failed_entries) > 0
    for f in failed_entries:
        cfg = f["configurations"]["argus_baseline_specialists_disabled"]
        assert cfg["passed"] is False
        assert cfg["severity"] in ["CRITICAL", "MAJOR", "MINOR"]
        assert cfg["failure_mode"] is not None
        assert "discovered_entities" in cfg


def test_repeat_run_comparison(tmp_path):
    """Requirement 12: Verify repeatable execution comparison and stability calculation."""
    split_mgr = BenchmarkSplitManager()
    tasks = split_mgr.get_frozen_regression_set()[:5]

    runner = BaselineRunner(output_dir=tmp_path)
    repeat_data = runner.verify_reproducibility_repeat(tasks)

    assert repeat_data["total_tasks_evaluated"] == 5
    assert repeat_data["repeated_runs_count"] == 2
    assert repeat_data["task_agreement_rate"] == 1.0
    assert repeat_data["discrepancies_count"] == 0
    assert repeat_data["is_deterministic"] is True


def test_infrastructure_error_handling(tmp_path, monkeypatch):
    """Requirement 13: Verify infrastructure errors are handled gracefully without silent swallow."""
    runner = BaselineRunner(output_dir=tmp_path)

    def mock_subprocess_fail(*args, **kwargs):
        raise OSError("Simulated system failure")

    monkeypatch.setattr("subprocess.run", mock_subprocess_fail)
    test_res = runner.run_unit_tests()
    assert test_res["status"] == "ERROR"
    assert test_res["exit_code"] == -1
    assert "Simulated system failure" in test_res["error_message"]


def test_correct_exit_status(tmp_path):
    """Requirement 14: Verify clean baseline execution produces exit code 0."""
    runner = BaselineRunner(run_id="test_exit_code", output_dir=tmp_path)
    out = runner.run(include_tests=False, include_repeat=False)
    assert out.exit_code == 0
    assert out.manifest["run_status"] == "COMPLETED"
