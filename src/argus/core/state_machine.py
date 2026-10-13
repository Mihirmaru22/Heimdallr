from datetime import UTC, datetime
from typing import ClassVar

from argus.domain.task import ResearchTask, TaskStatus


class InvalidStateTransitionError(Exception):
    """Raised when an illegal or out-of-lifecycle task state transition is attempted."""


class TaskStateMachine:
    """Enforces deterministic task lifecycle transitions and retry limits."""

    ALLOWED_TRANSITIONS: ClassVar[dict[TaskStatus, set[TaskStatus]]] = {
        TaskStatus.BLOCKED: {
            TaskStatus.READY,  # Dependency fulfilled
            TaskStatus.CANCELLED,  # Parent task failed or cancelled
        },
        TaskStatus.READY: {
            TaskStatus.RUNNING,  # Worker claimed task
            TaskStatus.BLOCKED,  # Rate-limited or paused for dependencies
            TaskStatus.CANCELLED,  # Aborted before execution
        },
        TaskStatus.RUNNING: {
            TaskStatus.COMPLETED,  # Execution succeeded
            TaskStatus.FAILED,  # Error occurred during execution
            TaskStatus.CANCELLED,  # Interrupted mid-flight
        },
        TaskStatus.FAILED: {
            TaskStatus.READY,  # Retry attempt
            TaskStatus.CANCELLED,  # Abandoned after failure
        },
        TaskStatus.COMPLETED: set(),  # Terminal state
        TaskStatus.CANCELLED: set(),  # Terminal state
    }

    @classmethod
    def can_transition(cls, current: TaskStatus, target: TaskStatus) -> bool:
        """Return True if transitioning from current to target status is valid."""
        return target in cls.ALLOWED_TRANSITIONS.get(current, set())

    @classmethod
    def transition(
        cls,
        task: ResearchTask,
        target: TaskStatus,
        error_message: str | None = None,
    ) -> ResearchTask:
        """
        Transition a ResearchTask to a new status.

        Validates the transition according to ALLOWED_TRANSITIONS and retry constraints.
        Raises InvalidStateTransitionError if the transition is prohibited.
        """
        if not cls.can_transition(task.status, target):
            raise InvalidStateTransitionError(
                f"Cannot transition task '{task.task_id}' from {task.status.value} to {target.value}."
            )

        # Retry constraint: FAILED -> READY
        if task.status == TaskStatus.FAILED and target == TaskStatus.READY:
            if task.retry_count >= task.max_retries:
                raise InvalidStateTransitionError(
                    f"Task '{task.task_id}' has reached maximum retries ({task.max_retries}) and cannot be requeued."
                )
            task.retry_count += 1

        task.status = target
        task.updated_at = datetime.now(UTC)

        if error_message is not None:
            task.error_message = error_message
        elif target == TaskStatus.COMPLETED:
            task.error_message = None

        return task
