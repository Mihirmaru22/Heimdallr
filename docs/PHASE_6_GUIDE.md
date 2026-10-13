# Phase 6 Implementation Guide: Research Brain & Orchestrator Controller

Welcome to **Phase 6** of Argus!

In this phase, you are building the **Research Brain and Orchestrator Controller**—the crowning layer of Argus V1.
By the end of Phase 6, all components built across Phases 0 through 5 (Domain Models, SQLite Repository, Search Pipeline, Crawler Fetcher, Worker Engine, and Expert Verifier) will be unified into a **fully autonomous, multi-turn intelligence loop**.

---

## 1. Architectural Principles (From the Brief)

1. **Model Specialization $\neq$ Agent Multiplication (Brief Sec 11):**
   * The **Research Brain** acts as the strategic executive (GLM 5.3 / Claude 3.5 / GPT-4o level reasoning).
   * It does not crawl or scrape itself; it decomposes objectives, assesses epistemic coverage, manages the task queue, and evaluates mathematical and heuristic stopping criteria.
2. **Two Decoupled Queues (Brief Sec 8):**
   * **Research Task Queue:** Strategic hypotheses and questions (*"Find plant manager of Kentucky Truck Plant"*).
   * **Crawl Request Queue:** Concrete URL fetching pipeline managed by the Crawler.
3. **Bounded & Resilient Execution (Brief Sec 12 & 16):**
   * Research runs must respect hard safety boundaries: `max_tasks`, `max_depth`, and query quotas.
   * If a search query returns 0 results or a URL times out, the task fails gracefully without halting the controller loop.
4. **Epistemic Stopping Invariant (Brief Sec 14):**
   * The controller halts when:
     1. All `required_fields` in `ResearchObjective` have `SUPPORTED` claims with high confidence ($\ge 0.85$).
     2. OR the safety budget (`max_tasks` or `max_depth`) is exhausted.
5. **Verified Intelligence Dossier (Brief Sec 15):**
   * Upon completion, Argus outputs an immutable, evidence-backed `ResearchDossier` summarizing discovered entities, corroborated claims, citations, audit statistics, and any active contradictions.

---

## 2. Directory Structure for Phase 6

```text
Argus/
├── docs/
│   ├── PHASE_0_GUIDE.md
│   ├── PHASE_1_GUIDE.md
│   ├── PHASE_2_GUIDE.md
│   ├── PHASE_3_GUIDE.md
│   ├── PHASE_4_GUIDE.md
│   ├── PHASE_5_GUIDE.md
│   └── PHASE_6_GUIDE.md          <-- NEW: Phase 6 Guide
├── src/
│   └── argus/
│       ├── core/
│       │   ├── state_machine.py
│       │   └── controller.py     <-- NEW: ArgusController (End-to-End Orchestrator)
│       ├── domain/
│       ├── storage/
│       ├── search/
│       ├── crawler/
│       ├── llm/
│       ├── worker/
│       ├── verifier/
│       └── brain/                <-- NEW: Strategic Research Brain
│           ├── __init__.py
│           ├── models.py         <-- TaskPlanningPayload, StoppingEvaluation, ResearchDossier
│           ├── prompts.py        <-- Strategic planning & dossier synthesis prompts
│           └── planner.py        <-- ResearchBrain (Decomposition, Stopping, Synthesis)
└── tests/
    ├── ...
    └── test_orchestrator.py      <-- NEW: End-to-end integration and orchestrator tests
```

---

## 3. Step-by-Step Code Specifications

### Step 6.1: Strategic Models (`src/argus/brain/models.py`)

```python
from pydantic import BaseModel, Field
from argus.domain.claim import Claim
from argus.domain.entity import Entity


class PlannedTask(BaseModel):
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    search_queries: list[str] = Field(default_factory=list)
    priority: int = Field(default=5, ge=1, le=10)


class TaskPlanningPayload(BaseModel):
    planned_tasks: list[PlannedTask]
    strategic_rationale: str


class StoppingEvaluation(BaseModel):
    should_stop: bool
    reason: str
    missing_fields: list[str] = Field(default_factory=list)
    coverage_score: float = Field(default=0.0, ge=0.0, le=1.0)


class DossierEntitySummary(BaseModel):
    entity: Entity
    supported_claims: list[Claim]
    contradicted_claims: list[Claim]


class ResearchDossier(BaseModel):
    objective_id: str
    target: str
    intelligence_goal: str
    executive_summary: str
    entities: list[DossierEntitySummary]
    total_tasks_executed: int
    total_documents_crawled: int
    unresolved_contradictions: int
    coverage_achieved: float
```

---

### Step 6.2: Strategic Brain (`src/argus/brain/planner.py`)

The strategic planner:
1. **Initial Task Decomposition:**
   * Given a new `ResearchObjective`, generates the initial batch of high-priority search and extraction tasks.
2. **Epistemic Coverage & Stopping Evaluation:**
   * Inspects current `SUPPORTED` claims against the objective's `required_fields`.
   * Evaluates if stopping conditions are satisfied:
     * Full coverage achieved, or
     * Task budget / recursion depth limits reached.
3. **Follow-Up Planning:**
   * If coverage is incomplete, plans targeted follow-up tasks (incorporating disambiguation requests from Phase 5).
4. **Final Synthesis:**
   * Synthesizes verified claims and entities into a cohesive `ResearchDossier`.

---

### Step 6.3: Orchestrator Controller (`src/argus/core/controller.py`)

The central execution engine uniting all phases:

```text
                         ┌─────────────────────────────┐
                         │   ResearchObjective Intake  │
                         └──────────────┬──────────────┘
                                        │
                                        ▼
                         ┌─────────────────────────────┐
                         │   ResearchBrain (Planner)   │ ◄──┐
                         │   Task Decomposition        │    │
                         └──────────────┬──────────────┘    │
                                        │                   │
                               Next READY Task              │
                                        │                   │
                                        ▼                   │
                         ┌─────────────────────────────┐    │
                         │    SearchPipeline (SearXNG) │    │
                         └──────────────┬──────────────┘    │
                                        │ URLs              │
                                        ▼                   │
                         ┌─────────────────────────────┐    │
                         │   TwoTierFetcher (Crawler)  │    │
                         └──────────────┬──────────────┘    │
                                        │ Documents         │
                                        ▼                   │
                         ┌─────────────────────────────┐    │
                         │   WorkerEngine (Extraction) │    │
                         └──────────────┬──────────────┘    │
                                        │ Pending Claims    │
                                        ▼                   │
                         ┌─────────────────────────────┐    │
                         │   ExpertVerifier (Adjudicate│    │
                         └──────────────┬──────────────┘    │
                                        │ Supported Claims  │
                                        ▼                   │
                         ┌─────────────────────────────┐    │
                         │   Evaluate Stopping Criteria├───┘
                         └──────────────┬──────────────┘
                                        │ Met / Budget Exhausted
                                        ▼
                         ┌─────────────────────────────┐
                         │   Final ResearchDossier     │
                         └─────────────────────────────┘
```

---

## 4. Test Strategy (`tests/test_orchestrator.py`)

The integration test suite must test the complete lifecycle in a fast, offline setting:

1. **`test_research_brain_task_decomposition`:**
   * Verifies initial objective produces prioritized tasks with search queries.
2. **`test_research_brain_stopping_evaluation`:**
   * Verifies stopping logic halts when required fields are satisfied or budget is exceeded.
3. **`test_orchestrator_end_to_end_mock_loop`:**
   * Wires together `SearchPipeline`, `TwoTierFetcher`, `WorkerEngine`, `ExpertVerifier`, and `ResearchBrain`.
   * Runs a full autonomous research cycle from objective intake to final `ResearchDossier`.
   * Asserts all tasks transition legally according to `TaskStateMachine`.
   * Asserts evidence, entities, claims, and audit events are properly persisted in SQLite.

---

## 5. Verification Commands

Once implemented, run:

```bash
uv run ruff check --fix . && uv run ruff format . && uv run pytest -v
```

All tests across Phases 0 through 6 must pass.
