"""Benchmark task suite manager and loader for Argus Evaluation.

Loads, validates, and filters versioned benchmark tasks and ground truth datasets.
"""

import json
from pathlib import Path
from typing import Any

from argus.evals.models import EvaluationTask, TaskCategory


DEFAULT_FIXTURES_DIR = Path(__file__).parent / "fixtures"
DEFAULT_TASKS_FILE = DEFAULT_FIXTURES_DIR / "tasks_v1.json"


class BenchmarkSuite:
    """Manages an immutable, versioned evaluation benchmark suite."""

    def __init__(self, tasks: list[EvaluationTask], version: str = "1.0") -> None:
        self.version = version
        self._tasks: dict[str, EvaluationTask] = {t.task_id: t for t in tasks}

    @property
    def tasks(self) -> list[EvaluationTask]:
        return list(self._tasks.values())

    def get_task(self, task_id: str) -> EvaluationTask | None:
        return self._tasks.get(task_id)

    def filter(
        self,
        category: TaskCategory | None = None,
        is_core: bool | None = None,
        difficulty: str | None = None,
        tag: str | None = None,
    ) -> list[EvaluationTask]:
        """Filter benchmark tasks by category, core subset, difficulty, or tag."""
        filtered = list(self._tasks.values())
        if category is not None:
            filtered = [t for t in filtered if t.category == category]
        if is_core is not None:
            filtered = [t for t in filtered if t.is_core == is_core]
        if difficulty is not None:
            filtered = [t for t in filtered if t.difficulty.value == difficulty or t.difficulty == difficulty]
        if tag is not None:
            filtered = [t for t in filtered if tag in t.tags]
        return filtered

    @classmethod
    def load_from_file(cls, path: Path | str | None = None) -> "BenchmarkSuite":
        """Load benchmark suite from JSON file."""
        file_path = Path(path) if path else DEFAULT_TASKS_FILE
        if not file_path.exists():
            raise FileNotFoundError(f"Benchmark tasks fixture not found at {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        raw_tasks = data.get("tasks", data) if isinstance(data, dict) else data
        tasks = [EvaluationTask.model_validate(t) for t in raw_tasks]
        version = data.get("version", "1.0") if isinstance(data, dict) else "1.0"
        return cls(tasks=tasks, version=version)

    @classmethod
    def load_core_subset(cls, path: Path | str | None = None) -> "BenchmarkSuite":
        """Convenience loader returning only the high-priority core validation tasks (5-10 tasks)."""
        suite = cls.load_from_file(path)
        core_tasks = suite.filter(is_core=True)
        return cls(tasks=core_tasks, version=suite.version)
