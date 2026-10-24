from app.models import JobState as S
from app.services.state_machine import ACTIVE, TERMINAL, TRANSITIONS, can_transition


def test_happy_path_is_allowed():
    path = [S.created, S.validating, S.planning, S.queued, S.running, S.validating_results, S.completed]
    for a, b in zip(path, path[1:], strict=False):
        assert can_transition(a, b), (a, b)


def test_terminal_states_only_allow_retry():
    assert not TRANSITIONS[S.completed] and not TRANSITIONS[S.partially_completed]
    assert can_transition(S.failed, S.queued) and can_transition(S.cancelled, S.queued)
    assert not can_transition(S.completed, S.running)


def test_cannot_skip_crawling():
    assert not can_transition(S.created, S.completed)
    assert not can_transition(S.queued, S.completed)


def test_every_state_classified():
    assert TERMINAL | ACTIVE == set(S)
    assert not TERMINAL & ACTIVE
