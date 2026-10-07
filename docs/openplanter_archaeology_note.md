# OpenPlanter Archaeology Note: Mechanism Breakdown vs. Argus Baseline

This document traces the exact code paths responsible for planning, task generation, search budgeting, and stopping behavior across OpenPlanter and the Argus baseline.

---

## 1. Mechanism Analysis

### Mechanism 1: Explicit Subtask Acceptance Criteria
- **OpenPlanter Implementation**:
  - `OpenPlanterSubtask.acceptance_criteria: str` in `openplanter_adapter.py`.
  - Every decomposed subtask specifies an explicit, verifiable acceptance threshold (e.g., `"Identified core facilities and headquarters for target"`).
- **Current Argus Equivalent**:
  - `TaskPlanningPayload.planned_tasks` in `src/argus/brain/prompts.py` and `src/argus/brain/planner.py`.
  - Tasks contain only unstructured `title`, `description`, and raw `search_queries`.
- **Exact Difference**:
  - Argus only evaluates acceptance and stopping *globally* across the entire objective (`evaluate_stopping_criteria`). Individual tasks have zero local acceptance criteria or stopping contracts; they execute open-endedly.
- **Expected Effect**:
  - Enforces local termination and focus on specific field verification, preventing the task from executing sprawling exploratory searches.
- **Risk**:
  - If acceptance criteria are formulated too narrowly by LLM decomposition, the worker may miss tangential high-value entities.

---

### Mechanism 2: Targeted Query Formulation vs. Archetype Dork Multiplication
- **OpenPlanter Implementation**:
  - `OpenPlanterAdapter.extract_search_queries`: Direct targeted queries matching the subtask's acceptance criteria (`base_queries[:4]`), with zero archetype dork multiplication.
  - Result in benchmark: **6.36 searches / task**.
- **Current Argus Equivalent**:
  - `ResearchBrain.extract_search_queries` + `_generate_archetype_dorks`:
  - When System 1 is active, multiplies each base query across newsroom (`site:linkedin.com/in`), regulatory (`site:gov`), directory (`facility directory`), and technical archetypes.
  - Result in benchmark: **12.36 searches / task**.
- **Exact Difference**:
  - Argus's archetype dorking quadruples search volume per task with broad exploratory phrases, flooding the candidate pool with non-target entities (suppliers, generic staff, directory lists).
- **Expected Effect**:
  - Binding search queries strictly to the task's target entity and acceptance criteria will drastically reduce search query spam and entity candidate set dilution, directly improving **entity precision**.
- **Risk**:
  - Removing dorking entirely might cause deep discovery failures on tasks requiring specific regulatory or directory lookups. The planner must generate targeted dorks *within* the acceptance criteria rather than blindly multiplying all queries.

---

### Mechanism 3: Bounded Recursive Subtask Decomposition vs. Facility Fan-Out
- **OpenPlanter Implementation**:
  - `OpenPlanterAdapter.plan_followup_tasks`:
  - Recurses generically on missing fields (`title = f"Investigate {field} for {objective.target}"`) up to depth 4.
  - No facility-level entity fan-out; no acronym canonicalization.
- **Current Argus Equivalent**:
  - `ResearchBrain.plan_followup_tasks`:
  - Domain-aware fan-out: When facility leadership fields are missing, lists all discovered facility entities (`facility_types`) and spawns dedicated subtasks for *each* individual facility (`"{fac.canonical_name}" plant manager OR director`).
- **Exact Difference**:
  - OpenPlanter recurred on broad target-level strings, which caused it to miss BlueOval City leadership and triggered the benchmark's only `EVIDENCE_ALIGNMENT_FAILURE`. Argus recurred on specific discovered sub-entities.
- **Expected Effect**:
  - Preserving Argus's domain-aware facility fan-out while adding OpenPlanter's bounded depth and acceptance criteria will maintain 100% evidence correctness while keeping high precision.
- **Risk**:
  - If recursive depth is too deep, task execution budgets (max 10-15 tasks) will be exhausted before core fields are satisfied.

---

### Mechanism 4: Task-Local Completion Decisions
- **OpenPlanter Implementation**:
  - Evaluates whether the subtask's acceptance criteria are met before recursing or halting.
- **Current Argus Equivalent**:
  - `ArgusController`: Automatically marks tasks `COMPLETED` after batch crawl/worker execution regardless of yield, relying on `consecutive_zero_yield_tasks` heuristic for diminishing returns.
- **Exact Difference**:
  - Argus treats task execution as a fire-and-forget batch step.
- **Expected Effect**:
  - Checking verified claims against task-local acceptance criteria allows the controller to know whether a child task is actually necessary.
- **Risk**:
  - If a task is marked failed or unsatisfied too aggressively, the controller might loop indefinitely if budget limits aren't enforced.

---

## 2. Summary Matrix

| OpenPlanter Mechanism | Current Argus Equivalent | Architectural Difference | Expected Benchmark Effect | Failure / Risk Profile |
| :--- | :--- | :--- | :--- | :--- |
| **Acceptance Criteria** | None (Unstructured `description`) | Local contract per task vs global objective stopping | Eliminates candidate entity set pollution; boosts Entity Precision | LLM hallucination of unachievable criteria |
| **Bounded Search Budgeting** | Archetype Dork Multiplication | 6.36 searches/task vs 12.36 searches/task | Cuts 48% search spam; prevents irrelevant page scraping | Missed edge-case regulatory filings |
| **Recursive Decomposition** | `plan_followup_tasks` with facility fan-out | Generic ReAct recursion vs Domain entity fan-out | Improves multi-hop navigation when combined | Evidence alignment failure if domain models omitted |
| **Local Task Completion** | Automatic unconditional `COMPLETED` transition | Evidence-based task verification vs batch completion | Prevents wasteful followups on satisfied fields | Premature task abandonment |
