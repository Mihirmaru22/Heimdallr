"""Tests for Eval V2 dataset splits, hidden adversarial holdout, and live holdout isolation."""

import pytest
from argus.evals.v2.holdout import BenchmarkSplitManager, LiveWebHoldoutHarness
from argus.evals.v2.models import BenchmarkSplit


def test_benchmark_split_isolation():
    mgr = BenchmarkSplitManager()
    dev = mgr.get_development_set()
    frozen = mgr.get_frozen_regression_set()
    hidden = mgr.get_hidden_adversarial_holdout()

    assert len(dev) > 0
    assert len(frozen) > 0
    assert len(hidden) > 0

    # Ensure mutually exclusive task IDs
    dev_ids = {t.task_id for t in dev}
    frozen_ids = {t.task_id for t in frozen}
    hidden_ids = {t.task_id for t in hidden}

    assert dev_ids.isdisjoint(frozen_ids)
    assert dev_ids.isdisjoint(hidden_ids)
    assert frozen_ids.isdisjoint(hidden_ids)

    # Check total sum equals all tasks
    total_split_tasks = len(dev) + len(frozen) + len(hidden)
    assert total_split_tasks == len(mgr.all_tasks)


def test_live_web_holdout_harness():
    mgr = BenchmarkSplitManager()
    task = mgr.all_tasks[0]
    harness = LiveWebHoldoutHarness()
    res = harness.execute_live_check(task)

    assert res["is_deterministic"] is False
    assert res["mode"] == "LIVE_WEB_HOLDOUT"
