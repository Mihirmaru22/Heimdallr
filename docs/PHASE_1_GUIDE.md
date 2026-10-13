# Phase 1 Implementation Guide: SQLite Storage & Observability

Welcome to **Phase 1** of Argus!

In this phase, you are building the **persistence engine and flight recorder**.
By the end of Phase 1, Argus will be able to store, query, and audit every research objective, task, discovered entity, factual claim, piece of evidence, and audit event into an embedded, high-performance SQLite database.

---

## 1. Directory Structure for Phase 1

You will create the `storage/` package and add the `event.py` model to `domain/`:

```text
Argus/
├── docs/
│   ├── PHASE_0_GUIDE.md
│   └── PHASE_1_GUIDE.md
├── src/
│   └── argus/
│       ├── core/
│       │   ├── __init__.py
│       │   └── state_machine.py
│       ├── domain/
│       │   ├── __init__.py
│       │   ├── objective.py
│       │   ├── task.py
│       │   ├── entity.py
│       │   ├── evidence.py
│       │   ├── claim.py
│       │   └── event.py             <-- NEW: Audit Log Event Model
│       └── storage/                 <-- NEW: SQLite Storage Engine
│           ├── __init__.py
│           ├── db.py                <-- Schema & Connection Manager
│           └── repository.py        <-- CRUD Operations for Models
└── tests/
    ├── test_objective.py
    ├── test_task.py
    ├── test_state_machine.py
    ├── test_knowledge_models.py
    └── test_storage.py              <-- NEW: Storage & Event Tests
```

---

## 2. Step-by-Step Implementation

### Step 1.1: `src/argus/domain/event.py` (The Flight Recorder)

#### **Concept & Purpose**
Every autonomous action Argus takes must be traceable (observability). 
When debugging an investigation, you must be able to answer:
* *What happened?* (`event_type`)
* *When did it happen?* (`timestamp`)
* *In context of which goal and task?* (`objective_id`, `task_id`)
* *What were the details?* (`payload`)

#### **Code Blueprint**
```python
from datetime import UTC, datetime
from enum import Enum
from typing import Any
import uuid
from pydantic import BaseModel, Field


class EventType(str, Enum):
    RESEARCH_STARTED = "research_started"
    RESEARCH_STOPPED = "research_stopped"

    TASK_CREATED = "task_created"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"

    SEARCH_EXECUTED = "search_executed"
    CRAWL_STARTED = "crawl_started"
    CRAWL_COMPLETED = "crawl_completed"
    DOCUMENT_CREATED = "document_created"

    ENTITY_EXTRACTED = "entity_extracted"
    CLAIM_CREATED = "claim_created"
    EVIDENCE_ATTACHED = "evidence_attached"

    VERIFICATION_STARTED = "verification_started"
    VERIFICATION_COMPLETED = "verification_completed"
    CONTRADICTION_DETECTED = "contradiction_detected"


def generate_event_id() -> str:
    return f"evt_{uuid.uuid4().hex[:8]}"


class ResearchEvent(BaseModel):
    """An immutable audit event recording an action during research."""

    event_id: str = Field(default_factory=generate_event_id)
    objective_id: str = Field(..., min_length=1)
    task_id: str | None = None
    event_type: EventType
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

---

### Step 1.2: `src/argus/storage/db.py` (Database & Schema Engine)

#### **Concept & Purpose**
Uses Python's built-in `sqlite3` driver. 
It creates all tables with proper indexes and ensures SQLite is running with:
1. `PRAGMA foreign_keys = ON;` (Referential integrity)
2. `PRAGMA journal_mode = WAL;` (Write-Ahead Logging for high-concurrency read/writes)

#### **Database Tables Needed**
1. `objectives`: Stores `ResearchObjective` (JSON serialization for `required_fields`).
2. `tasks`: Stores `ResearchTask` (FK to objectives, status, priority, depth, retries).
3. `entities`: Stores `Entity` (JSON for `aliases` and `attributes`).
4. `evidence`: Stores `Evidence` (URL, quote passage, character offsets, confidence).
5. `claims`: Stores `Claim` (FK to subject entity, JSON for `evidence_ids`).
6. `events`: Stores `ResearchEvent` (FK to objective and task, JSON for `payload`).

#### **Schema DDL Blueprint**
```sql
CREATE TABLE IF NOT EXISTS objectives (
    objective_id TEXT PRIMARY KEY,
    target TEXT NOT NULL,
    target_type TEXT NOT NULL,
    intelligence_goal TEXT NOT NULL,
    required_fields TEXT NOT NULL,  -- JSON string list
    success_criteria TEXT NOT NULL,
    max_tasks INTEGER NOT NULL,
    max_depth INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    objective_id TEXT NOT NULL,
    parent_task_id TEXT,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL,
    priority INTEGER NOT NULL,
    depth INTEGER NOT NULL,
    retry_count INTEGER NOT NULL,
    max_retries INTEGER NOT NULL,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(objective_id) REFERENCES objectives(objective_id)
);

CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    aliases TEXT NOT NULL,          -- JSON string list
    attributes TEXT NOT NULL,       -- JSON string dict
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    url TEXT NOT NULL,
    passage TEXT NOT NULL,
    char_start INTEGER,
    char_end INTEGER,
    confidence REAL NOT NULL,
    retrieved_at TEXT NOT NULL,
    published_at TEXT
);

CREATE TABLE IF NOT EXISTS claims (
    claim_id TEXT PRIMARY KEY,
    subject_entity_id TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object_value TEXT NOT NULL,
    object_entity_id TEXT,
    status TEXT NOT NULL,
    evidence_ids TEXT NOT NULL,     -- JSON string list
    confidence REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(subject_entity_id) REFERENCES entities(entity_id)
);

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    objective_id TEXT NOT NULL,
    task_id TEXT,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,          -- JSON string dict
    timestamp TEXT NOT NULL,
    FOREIGN KEY(objective_id) REFERENCES objectives(objective_id)
);

-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_tasks_objective ON tasks(objective_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_claims_subject ON claims(subject_entity_id);
CREATE INDEX IF NOT EXISTS idx_events_objective ON events(objective_id);
```

#### **Database Manager Class (`DatabaseManager`)**
```python
import sqlite3
from pathlib import Path


class DatabaseManager:
    def __init__(self, db_path: str | Path = ":memory:"):
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        with self.conn:
            self.conn.execute("PRAGMA foreign_keys = ON;")
            if self.db_path != ":memory:":
                self.conn.execute("PRAGMA journal_mode = WAL;")
            self.conn.executescript(SCHEMA_SQL)

    def close(self) -> None:
        self.conn.close()
```

---

### Step 1.3: `src/argus/storage/repository.py` (The Repository Pattern)

#### **Concept & Purpose**
Provides clean Python methods so the rest of the application never writes raw SQL.
It automatically handles converting between **Pydantic models** and **SQLite rows** (including JSON serialization for lists and dictionaries).

#### **Required Repository Methods**

##### Objectives
* `save_objective(objective: ResearchObjective) -> None`
* `get_objective(objective_id: str) -> ResearchObjective | None`

##### Tasks
* `save_task(task: ResearchTask) -> None` (INSERT or UPDATE / UPSERT)
* `get_task(task_id: str) -> ResearchTask | None`
* `list_tasks(objective_id: str, status: TaskStatus | None = None) -> list[ResearchTask]`

##### Entities
* `save_entity(entity: Entity) -> None`
* `get_entity(entity_id: str) -> Entity | None`
* `list_entities(entity_type: str | None = None) -> list[Entity]`

##### Evidence
* `save_evidence(evidence: Evidence) -> None`
* `get_evidence(evidence_id: str) -> Evidence | None`

##### Claims
* `save_claim(claim: Claim) -> None`
* `get_claim(claim_id: str) -> Claim | None`
* `list_claims(subject_entity_id: str | None = None, status: ClaimStatus | None = None) -> list[Claim]`

##### Events
* `record_event(event: ResearchEvent) -> None`
* `list_events(objective_id: str) -> list[ResearchEvent]`

---

## 3. Writing Unit Tests (`tests/test_storage.py`)

Using SQLite in-memory mode (`:memory:`), tests run in milliseconds without creating lingering test database files.

### Test Scenarios to Cover
1. **Objective CRUD:** Insert `ResearchObjective`, retrieve it by ID, and verify `required_fields` list parsed correctly.
2. **Task Upsert:** Insert a task as `READY`, update to `RUNNING`, update to `COMPLETED`, verify `list_tasks(status=COMPLETED)` returns it.
3. **Knowledge Graph Linking:** Insert an `Entity`, insert `Evidence`, insert a `Claim` referencing them both, and verify foreign key consistency.
4. **Audit Log Trail:** Record 3 events (`RESEARCH_STARTED`, `TASK_CREATED`, `TASK_COMPLETED`), query `list_events(objective_id)`, and assert ordering and payload integrity.

---

## 4. Verification Command

Run:
```bash
uv run pytest -v tests/test_storage.py
```

When all tests pass, **Phase 1 is complete!** Argus has a persistent, fully auditable database.
