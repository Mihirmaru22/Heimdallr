"""The benchmark does not start when today's free model allowance cannot cover its runs."""

import pytest

from app import cli


class State:
    def __init__(self, used):
        self.used = used

    def daily_limit(self):
        return 1000

    def used_today(self):
        return self.used

    def exhausted(self):
        return False


def test_a_benchmark_the_allowance_cannot_cover_is_not_started(monkeypatch):
    monkeypatch.setattr("app.llm.openrouter.State", lambda: State(842))
    monkeypatch.setattr("app.services.evaluation.start_runs", lambda *a: pytest.fail("runs were started"))
    with pytest.raises(SystemExit, match="158 of 1000 free model requests are left"):
        cli.eval_run(wait_seconds=1, repeat=2)
