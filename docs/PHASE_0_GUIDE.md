# Phase 0 Implementation Guide: Foundation & Domain Models

Welcome to **Phase 0** of Argus! In this phase, you are building the **data foundation and code invariants** of the system.

By the end of this phase, you will have a working, test-verified foundation where:
1. **Objectives** can be specified with stopping criteria and safety budgets.
2. **Tasks** can be created, queued, and tracked.
3. **The Task State Machine** deterministically controls task lifecycles, forbidding illegal transitions and handling retries.
4. **Knowledge Models** (Entity, Claim, Evidence) strictly define the epistemic graph.
5. All code is validated by a clean suite of `pytest` unit tests.

---

## 1. Directory Structure to Create

Inside `src/argus/` and `tests/`, you will create the following structure:

```text
Argus/
├── pyproject.toml
├── README.md
├── src/
│   └── argus/
│       ├── __init__.py
│       ├── core/
│       │   ├── __init__.py
│       │   └── state_machine.py      <-- The Transition Engine
│       └── domain/
│           ├── __init__.py
│           ├── objective.py          <-- ResearchObjective
│           ├── task.py               <-- TaskStatus & ResearchTask
│           ├── entity.py             <-- Entity
│           ├── evidence.py           <-- Evidence
│           └── claim.py              <-- Claim & ClaimStatus
└── tests/
    ├── __init__.py
    ├── test_objective.py
    ├── test_task.py
    ├── test_state_machine.py
    └── test_knowledge_models.py
```

---

## 2. Step-by-Step Hand-Holding Walkthrough

### Step 0.1: `src/argus/domain/objective.py` (The Mission Contract)

#### **Concept & Purpose**
The `ResearchObjective` is the user-provided goal that kicks off an Argus investigation. It tells the Planning Agent what information to look for, what fields are strictly required, and sets operational safety limits so the agent cannot loop forever.

#### **Fields & Types**
```python
from datetime import datetime, timezone
import uuid
from pydantic import BaseModel, Field


def generate_objective_id() -> str:
    return f"obj_{uuid.uuid4().hex[:8]}"


class ResearchObjective(BaseModel):
    objective_id: str = Field(default_factory=generate_objective_id)
    target: str  # e.g., "US-origin automobile manufacturers"
    target_type: str  # e.g., "industry", "company", "facility"
    intelligence_goal: str  # High-level query/intent
    required_fields: list[str]  # e.g., ["plants", "addresses", "plant_leaders"]
    success_criteria: str  # Stopping condition
    max_tasks: int = 50  # Operational safety limit
    max_depth: int = 3  # Max task tree recursion depth
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

#### **Key Validations to Include**
* Ensure `target` is not blank.
* Ensure `required_fields` contains at least one field.
* Ensure `max_tasks > 0`.

---

### Step 0.2: `src/argus/domain/task.py` (The Atomic Research Unit)

#### **Concept & Purpose**
The Planning Agent breaks down the objective into individual, atomic research questions (e.g., *"Find the plant manager of Kentucky Truck Plant"*). Every task has a priority, a depth, a parent pointer, and an execution lifecycle state.

#### **Fields & Types**
```python
from datetime import datetime, timezone
from enum import Enum
import uuid
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    READY = "ready"  # Ready to be picked up by a worker
    RUNNING = "running"  # Worker is executing
    COMPLETED = "completed"  # Successfully finished
    FAILED = "failed"  # Execution failed / error
    BLOCKED = "blocked"  # Waiting on a parent task
    CANCELLED = "cancelled"  # Aborted


def generate_task_id() -> str:
    return f"tsk_{uuid.uuid4().hex[:8]}"


class ResearchTask(BaseModel):
    task_id: str = Field(default_factory=generate_task_id)
    objective_id: str  # Foreign key linking back to the ResearchObjective
    parent_task_id: str | None = None  # None for root tasks; ID if subtask
    title: str  # Short human-readable title
    description: str  # Specific instructions for the Worker
    status: TaskStatus = TaskStatus.READY
    priority: int = 1  # 1 (low) to 100 (high) for queue order
    depth: int = 0  # 0 for root tasks; parent.depth + 1 for subtasks
    retry_count: int = 0
    max_retries: int = 3
    error_message: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

---

### Step 0.3: `src/argus/core/state_machine.py` (The Invariant Traffic Light)

#### **Concept & Purpose**
This is a **System 0 (Code Invariant)** component. No model, worker, or tool is allowed to bypass the state machine. It prevents invalid status changes (such as completing an unstarted task or retrying beyond the maximum retry limit).

#### **The Lifecycle Transition Rules**
* `BLOCKED` $\to$ `READY` (dependency fulfilled) or `CANCELLED` (parent failed)
* `READY` $\to$ `RUNNING` (worker claimed task), `BLOCKED` (paused/rate-limited), `CANCELLED`
* `RUNNING` $\to$ `COMPLETED` (success), `FAILED` (error), `CANCELLED`
* `FAILED` $\to$ `READY` (retry attempt, if `retry_count < max_retries`), `CANCELLED`
* `COMPLETED` $\to$ *(None — Terminal State)*
* `CANCELLED` $\to$ *(None — Terminal State)*

#### **Class Implementation Blueprint**
```python
from datetime import datetime, timezone
from argus.domain.task import ResearchTask, TaskStatus


class InvalidStateTransitionError(Exception):
    """Raised when an illegal task transition is attempted."""

    pass


class TaskStateMachine:
    ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
        TaskStatus.BLOCKED: {TaskStatus.READY, TaskStatus.CANCELLED},
        TaskStatus.READY: {
            TaskStatus.RUNNING,
            TaskStatus.BLOCKED,
            TaskStatus.CANCELLED,
        },
        TaskStatus.RUNNING: {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        },
        TaskStatus.FAILED: {TaskStatus.READY, TaskStatus.CANCELLED},
        TaskStatus.COMPLETED: set(),  # Terminal
        TaskStatus.CANCELLED: set(),  # Terminal
    }

    @classmethod
    def can_transition(cls, current: TaskStatus, target: TaskStatus) -> bool:
        return target in cls.ALLOWED_TRANSITIONS.get(current, set())

    @classmethod
    def transition(
        cls,
        task: ResearchTask,
        target: TaskStatus,
        error_message: str | None = None,
    ) -> ResearchTask:
        if not cls.can_transition(task.status, target):
            raise InvalidStateTransitionError(
                f"Cannot transition task '{task.task_id}' from {task.status.value} to {target.value}."
            )

        # Handle retry logic: FAILED -> READY
        if task.status == TaskStatus.FAILED and target == TaskStatus.READY:
            if task.retry_count >= task.max_retries:
                raise InvalidStateTransitionError(
                    f"Task '{task.task_id}' has exceeded max retries ({task.max_retries})."
                )
            task.retry_count += 1

        task.status = target
        task.updated_at = datetime.now(timezone.utc)
        if error_message is not None:
            task.error_message = error_message
        elif target == TaskStatus.COMPLETED:
            task.error_message = None

        return task
```

---

### Step 0.4: Epistemic Knowledge Models

In Argus, the core epistemological rule is: **Entity $\to$ Claim $\to$ Evidence $\to$ Source**.

#### 1. `src/argus/domain/entity.py`
Represents a distinct real-world target (Person, Company, Facility).
```python
from datetime import datetime, timezone
from typing import Any
import uuid
from pydantic import BaseModel, Field


def generate_entity_id() -> str:
    return f"ent_{uuid.uuid4().hex[:8]}"


class Entity(BaseModel):
    entity_id: str = Field(default_factory=generate_entity_id)
    entity_type: str  # e.g., "company", "facility", "person"
    canonical_name: str  # e.g., "Ford Motor Company"
    aliases: list[str] = Field(default_factory=list)  # e.g., ["Ford", "FoMoCo"]
    attributes: dict[str, Any] = Field(
        default_factory=dict
    )  # e.g., {"website": "ford.com"}
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

#### 2. `src/argus/domain/evidence.py`
The unshakeable citation and proof backing a claim.
```python
from datetime import datetime, timezone
import uuid
from pydantic import BaseModel, Field


def generate_evidence_id() -> str:
    return f"evi_{uuid.uuid4().hex[:8]}"


class Evidence(BaseModel):
    evidence_id: str = Field(default_factory=generate_evidence_id)
    source_id: str  # Reference to document or crawl source
    url: str  # Source URL
    passage: str  # The exact raw snippet/quote
    char_start: int | None = None  # Character offset in raw document
    char_end: int | None = None  # Character offset in raw document
    confidence: float = 1.0  # Epistemic confidence score (0.0 to 1.0)
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    published_at: datetime | None = None
```

#### 3. `src/argus/domain/claim.py`
The atomic factual assertion (`Subject -> Predicate -> Object`).
```python
from datetime import datetime, timezone
from enum import Enum
import uuid
from pydantic import BaseModel, Field


class ClaimStatus(str, Enum):
    PENDING = "pending"  # Newly extracted, not yet verified
    SUPPORTED = "supported"  # Backed by valid evidence
    REFUTED = "refuted"  # Proven false by reliable source
    UNVERIFIED = "unverified"  # Cannot corroborate
    CONTRADICTED = "contradicted"  # Disputed by conflicting sources


def generate_claim_id() -> str:
    return f"clm_{uuid.uuid4().hex[:8]}"


class Claim(BaseModel):
    claim_id: str = Field(default_factory=generate_claim_id)
    subject_entity_id: str  # FK to Entity (e.g. Kentucky Truck Plant)
    predicate: str  # e.g., "HAS_PLANT_MANAGER", "LOCATED_IN"
    object_value: str  # String value, or name
    object_entity_id: str | None = None  # FK to another Entity if applicable
    status: ClaimStatus = ClaimStatus.PENDING
    evidence_ids: list[str] = Field(default_factory=list)  # Traceable citations
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

---

## 3. Writing Unit Tests (`tests/`)

Write 4 test files to prove your Phase 0 implementation works flawlessly:

### `tests/test_objective.py`
* Test default ID generation and default timestamps.
* Test validation of required fields and non-empty target.

### `tests/test_task.py`
* Test task creation with `READY` status.
* Test priority and depth assignments.

### `tests/test_state_machine.py`
* Test standard happy path: `READY -> RUNNING -> COMPLETED`.
* Test error path: `READY -> RUNNING -> FAILED`.
* Test retry path: `FAILED -> READY` increments `retry_count`.
* Test max retries exceeded raises `InvalidStateTransitionError`.
* Test illegal transition: `COMPLETED -> RUNNING` raises `InvalidStateTransitionError`.
* Test blocked task: `BLOCKED -> RUNNING` raises `InvalidStateTransitionError`.

### `tests/test_knowledge_models.py`
* Test creating an `Entity`, adding aliases and attributes.
* Test creating an `Evidence` item with source URL and passage.
* Test creating a `Claim` linked to the entity and evidence IDs.

---

## 4. Verification Command

Once implemented, run:
```bash
uv run pytest -v
```

When all tests pass green, **Phase 0 is complete and certified!** 🎯
