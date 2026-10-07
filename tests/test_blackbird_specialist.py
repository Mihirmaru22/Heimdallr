"""Unit tests for Blackbird specialist and vertical identity correlation."""

import pytest
from argus.evals.vertical_corpus import VERTICAL_PLATFORM_REGISTRY
from argus.evals.vertical_runner import VerticalBenchmarkRunner
from argus.specialists.blackbird_specialist import BlackbirdSpecialist


def test_blackbird_specialist_finds_accounts():
    specialist = BlackbirdSpecialist(platform_corpus=VERTICAL_PLATFORM_REGISTRY)
    res = specialist.search_username("s0md3v")
    assert res.total_found >= 3
    urls = [a.url for a in res.accounts_found]
    assert "https://github.com/s0md3v" in urls
    assert "https://twitter.com/s0md3v" in urls


def test_blackbird_specialist_phantom_returns_zero():
    specialist = BlackbirdSpecialist(platform_corpus=VERTICAL_PLATFORM_REGISTRY)
    res = specialist.search_username("nonexistent_phantom_handle_987654321_xyz")
    assert res.total_found == 0


def test_vertical_benchmark_runner_argus_baseline():
    runner = VerticalBenchmarkRunner()
    res = runner.run_argus_baseline(runner.tasks[0])  # s0md3v
    # Argus baseline misses Twitter/Medium due to lack of probe engine
    assert res.candidate_recall < 1.0


def test_vertical_benchmark_runner_integrated_disambiguation():
    runner = VerticalBenchmarkRunner()
    # Task 4 is Joe Bobnar with conflicting Twitch gamer
    res = runner.run_integrated(runner.tasks[3])
    assert res.passed is True
    # Twitch gamer was rejected by verifier!
    assert "https://twitch.tv/jbobnar" not in res.discovered_accounts
    assert "https://linkedin.com/in/jbobnar" in res.discovered_accounts
