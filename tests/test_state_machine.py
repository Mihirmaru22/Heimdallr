import pytest

from argus.core.state_machine import InvalidStateTransitionError, TaskStateMachine
from argus.domain.task import ResearchTask, TaskStatus


def make_task(**kwargs) -> ResearchTask:
    defaults = {
        "objective_id": "obj_test",
        "title": "Test Task",
        "description": "Test Description",
    }
    defaults.update(kwargs)
    return ResearchTask(**defaults)


def test_happy_path_lifecycle():
    task = make_task()
    assert task.status == TaskStatus.READY

    # READY -> RUNNING
    TaskStateMachine.transition(task, TaskStatus.RUNNING)
    assert task.status == TaskStatus.RUNNING

    # RUNNING -> COMPLETED
    TaskStateMachine.transition(task, TaskStatus.COMPLETED)
    assert task.status == TaskStatus.COMPLETED
    assert task.error_message is None


def test_failure_and_retry_flow():
    task = make_task(max_retries=2)
    assert task.retry_count == 0

    # RUNNING -> FAILED
    TaskStateMachine.transition(task, TaskStatus.RUNNING)
    TaskStateMachine.transition(task, TaskStatus.FAILED, error_message="HTTP 500 error")
    assert task.status == TaskStatus.FAILED
    assert task.error_message == "HTTP 500 error"

    # Retry 1: FAILED -> READY
    TaskStateMachine.transition(task, TaskStatus.READY)
    assert task.status == TaskStatus.READY
    assert task.retry_count == 1

    # Retry 2: RUNNING -> FAILED -> READY
    TaskStateMachine.transition(task, TaskStatus.RUNNING)
    TaskStateMachine.transition(task, TaskStatus.FAILED, error_message="Rate limit")
    TaskStateMachine.transition(task, TaskStatus.READY)
    assert task.retry_count == 2

    # Fail again and try 3rd retry (exceeds max_retries=2)
    TaskStateMachine.transition(task, TaskStatus.RUNNING)
    TaskStateMachine.transition(task, TaskStatus.FAILED, error_message="Fatal crash")
    with pytest.raises(InvalidStateTransitionError, match="maximum retries"):
        TaskStateMachine.transition(task, TaskStatus.READY)


def test_terminal_states_cannot_transition():
    # Completed task cannot change state
    completed_task = make_task(status=TaskStatus.COMPLETED)
    with pytest.raises(InvalidStateTransitionError):
        TaskStateMachine.transition(completed_task, TaskStatus.RUNNING)

    with pytest.raises(InvalidStateTransitionError):
        TaskStateMachine.transition(completed_task, TaskStatus.READY)

    # Cancelled task cannot change state
    cancelled_task = make_task(status=TaskStatus.CANCELLED)
    with pytest.raises(InvalidStateTransitionError):
        TaskStateMachine.transition(cancelled_task, TaskStatus.READY)


def test_blocked_task_lifecycle():
    blocked_task = make_task(status=TaskStatus.BLOCKED)

    # Cannot jump directly to RUNNING
    with pytest.raises(InvalidStateTransitionError):
        TaskStateMachine.transition(blocked_task, TaskStatus.RUNNING)

    # Can unblock to READY
    TaskStateMachine.transition(blocked_task, TaskStatus.READY)
    assert blocked_task.status == TaskStatus.READY


def test_cancellation_from_multiple_states():
    # From READY
    t1 = make_task(status=TaskStatus.READY)
    TaskStateMachine.transition(t1, TaskStatus.CANCELLED)
    assert t1.status == TaskStatus.CANCELLED

    # From RUNNING
    t2 = make_task(status=TaskStatus.RUNNING)
    TaskStateMachine.transition(t2, TaskStatus.CANCELLED)
    assert t2.status == TaskStatus.CANCELLED

    # From BLOCKED
    t3 = make_task(status=TaskStatus.BLOCKED)
    TaskStateMachine.transition(t3, TaskStatus.CANCELLED)
    assert t3.status == TaskStatus.CANCELLED
