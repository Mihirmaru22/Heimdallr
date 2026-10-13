"""P0.3-R: BENCHMARK INDEPENDENCE REGRESSION TEST SUITE.

Verifies that the production research engine does NOT contain benchmark-specific
task IDs, hardcoded executive rosters, hardcoded contradiction pairs, or
injected task outcomes in:
- src/argus/investigation/orchestrator.py
- src/argus/investigation/planner.py
- src/argus/investigation/stopping.py
- src/argus/investigation/state.py
- src/argus/investigation/question.py
- src/argus/investigation/information_gain.py
"""

from __future__ import annotations

import re
from pathlib import Path
import pytest

PRODUCTION_FILES = [
    Path("src/argus/investigation/orchestrator.py"),
    Path("src/argus/investigation/planner.py"),
    Path("src/argus/investigation/stopping.py"),
    Path("src/argus/investigation/state.py"),
    Path("src/argus/investigation/question.py"),
    Path("src/argus/investigation/information_gain.py"),
    Path("src/argus/investigation/branch.py"),
    Path("src/argus/investigation/evidence.py"),
    Path("src/argus/investigation/hypothesis.py"),
]

FORBIDDEN_TASK_IDS = [
    r"\binv_task_\w+",
    r"\bbenchmark_task_\w+",
]

# The 20 executive names from the benchmark task
BENCHMARK_EXECUTIVE_NAMES = [
    "Arthur D. Levinson",
    "Katherine L. Adams",
    "Luca Maestri",
    "Deirdre O'Brien",
    "Sabih Khan",
    "Craig Federighi",
    "Eddy Cue",
    "John Giannandrea",
    "Greg Joswiak",
    "John Ternus",
    "Johny Srouji",
    "Jeff Williams",
    "Adrian Perica",
    "Carol Surface",
    "Tor Myhren",
    "Frank X. Casanova",
    "Isabel Ge Mahe",
    "Kristin Huguet Quayle",
    "Lisa Jackson",
    "Kevan Parekh",
]

# Benchmark-specific contradiction entities/strings
BENCHMARK_CONTRADICTION_STRINGS = [
    "Drake Equation",
    "Ole Rømer",
    "Christiaan Huygens",
    "Hubble Constant Tension",
    "Microwave quantum illumination",
    "Factor N",
]

# Benchmark-specific negative/adversarial task strings
BENCHMARK_NEGATIVE_STRINGS = [
    "LUX-ZEPLIN",
    "LK-99",
    "Voynich",
    "Liz Truss",
    "SEC Bitcoin",
]


@pytest.mark.parametrize("file_path", PRODUCTION_FILES)
def test_no_benchmark_task_ids_in_production(file_path: Path):
    """Production code must not mention benchmark task IDs."""
    assert file_path.exists(), f"File {file_path} must exist"
    content = file_path.read_text(encoding="utf-8")
    for pattern in FORBIDDEN_TASK_IDS:
        matches = re.findall(pattern, content)
        assert not matches, f"Found benchmark task ID pattern '{pattern}' in {file_path}: {matches}"


@pytest.mark.parametrize("file_path", PRODUCTION_FILES)
def test_no_hardcoded_executive_roster_in_production(file_path: Path):
    """Production code must not contain hardcoded lists of the benchmark 20 executives."""
    assert file_path.exists(), f"File {file_path} must exist"
    content = file_path.read_text(encoding="utf-8")
    for name in BENCHMARK_EXECUTIVE_NAMES:
        assert name not in content, f"Found benchmark executive name '{name}' in {file_path}"


@pytest.mark.parametrize("file_path", PRODUCTION_FILES)
def test_no_hardcoded_contradiction_strings_in_production(file_path: Path):
    """Production code must not hardcode answers to benchmark contradiction tasks."""
    assert file_path.exists(), f"File {file_path} must exist"
    content = file_path.read_text(encoding="utf-8")
    for s in BENCHMARK_CONTRADICTION_STRINGS:
        assert s not in content, f"Found benchmark contradiction string '{s}' in {file_path}"


@pytest.mark.parametrize("file_path", PRODUCTION_FILES)
def test_no_hardcoded_negative_case_strings_in_production(file_path: Path):
    """Production code must not hardcode answers to benchmark negative/adversarial tasks."""
    assert file_path.exists(), f"File {file_path} must exist"
    content = file_path.read_text(encoding="utf-8")
    for s in BENCHMARK_NEGATIVE_STRINGS:
        assert s not in content, f"Found benchmark negative/adversarial string '{s}' in {file_path}"


def test_runtime_engine_has_no_access_to_benchmark_evaluator():
    """Verify production engine does not import benchmark evaluator or tasks."""
    for f in PRODUCTION_FILES:
        content = f.read_text(encoding="utf-8")
        assert "from argus.investigation.benchmark.evaluator" not in content
        assert "from argus.investigation.benchmark.tasks" not in content
