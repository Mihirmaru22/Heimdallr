"""A job's model calls, per step, as the job report and the scorecard print them."""

from types import SimpleNamespace

from app.services.common import model_call_lines, model_calls


def test_the_calls_a_job_stored_are_read_back_per_step_with_the_plan_s():
    job = SimpleNamespace(id="j", schema_id="s", counters={
        "model_calls_kept": 1, "fetched": 12,
        "model_calls.proof_read.answered": 30, "model_calls.proof_read.failed": 9,
        "model_calls.second_read.answered": 2, "plan_model_calls.plan.answered": 1})
    calls, plan = model_calls(job)
    assert calls == {"proof_read": {"answered": 30, "failed": 9}, "second_read": {"answered": 2, "failed": 0}}
    assert plan == {"plan": {"answered": 1, "failed": 0}}
    lines = dict(model_call_lines(job))
    assert lines["model calls"] == "total 42: answered 33, failed 9"
    assert lines["model calls: proof_read"] == "total 39: answered 30, failed 9"
    assert lines["model calls: plan"] == "total 1: answered 1, failed 0"
