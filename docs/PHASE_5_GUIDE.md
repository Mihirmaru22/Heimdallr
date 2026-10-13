# Phase 5 Implementation Guide: Expert Verifier & Adjudication Layer

Welcome to **Phase 5** of Argus!

In this phase, you are building the **Expert Verifier and Adjudication Layer**. 
By the end of Phase 5, Argus will be able to analyze candidate claims extracted by workers, detect factual contradictions across multiple web sources, corroborate agreeing evidence, resolve temporal and authoritative conflicts, and transition claims from `PENDING` into `SUPPORTED`, `CONTRADICTED`, or `REFUTED`.

---

## 1. Architectural Principles (From the Brief)

1. **Model Specialization $\neq$ Agent Multiplication (Brief Sec 11):**
   * While Workers use fast, high-throughput models (DeepSeek Flash) for extraction, the **Expert Verifier** uses an analytical model (DeepSeek Pro) specialized in logical reasoning, evidence synthesis, and bias/recency adjudication.
2. **Epistemic States (Brief Sec 10):**
   * Claims start in `PENDING`.
   * **`SUPPORTED`**: Confirmed by multiple independent sources or authoritative corporate/official domain evidence with high confidence ($\ge 0.85$).
   * **`CONTRADICTED`**: Irreconcilable conflict between active sources (e.g. Source A claims Plant Manager is "Jane Doe", Source B claims Plant Manager is "Bob Smith") that cannot be definitively resolved without further targeted investigation.
   * **`REFUTED`**: Authoritatively superseded or disproven (e.g., an older 2021 claim disproven by a 2026 official press release).
   * **`UNVERIFIED`**: Single weak source with insufficient corroboration.
3. **Temporal Supersession & Source Authority:**
   * Facts change over time (e.g., executive turnover, facility re-tooling). When two sources disagree, the Verifier analyzes source publication dates, document timestamps, and domain authority to decide if one claim supersedes the other.
4. **Disambiguation Task Generation:**
   * When an active contradiction cannot be resolved with existing evidence, the Verifier generates a targeted disambiguation query (e.g. *"Verify current plant manager of Kentucky Truck Plant as of 2026"*) to feed the Research Task queue.

---

## 2. Directory Structure for Phase 5

```text
Argus/
├── docs/
│   ├── PHASE_0_GUIDE.md
│   ├── PHASE_1_GUIDE.md
│   ├── PHASE_2_GUIDE.md
│   ├── PHASE_3_GUIDE.md
│   ├── PHASE_4_GUIDE.md
│   └── PHASE_5_GUIDE.md          <-- NEW: Phase 5 Guide
├── src/
│   └── argus/
│       ├── core/
│       ├── domain/
│       ├── storage/
│       ├── search/
│       ├── crawler/
│       ├── llm/
│       ├── worker/
│       └── verifier/             <-- NEW: Expert Verifier Layer
│           ├── __init__.py
│           ├── models.py         <-- Adjudication schemas & verdicts
│           ├── prompts.py        <-- Verifier prompts & reasoning templates
│           └── engine.py         <-- ExpertVerifier (Conflict grouping, Adjudication, Repository update)
└── tests/
    ├── test_worker.py
    ├── ...
    └── test_verifier.py          <-- NEW: Verifier & Adjudication Test Suite
```

---

## 3. Step-by-Step Code Specifications

### Step 5.1: Adjudication Models (`src/argus/verifier/models.py`)

```python
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field
from argus.domain.claim import ClaimStatus


class VerdictType(str, Enum):
    CORROBORATED = "corroborated"  # Multiple sources confirm same fact
    SUPERSEDED = "superseded"  # Newer authoritative source overrides older claim
    CONTRADICTION = "contradiction"  # Unresolved dispute between sources
    INSUFFICIENT = "insufficient"  # Weak or isolated single-source claim


class ClaimEvaluation(BaseModel):
    """Adjudicated evaluation for an individual claim."""

    claim_id: str
    status: ClaimStatus
    confidence: float = Field(..., ge=0.0, le=1.0)
    verdict: VerdictType
    reasoning: str


class AdjudicationPayload(BaseModel):
    """Structured output returned by the Expert Verifier LLM."""

    evaluations: list[ClaimEvaluation]
    has_conflict: bool
    summary_reasoning: str
    suggested_disambiguation_tasks: list[str] = Field(default_factory=list)


class AdjudicationResult(BaseModel):
    """Summary of adjudication run across a group of claims."""

    subject_entity_id: str
    predicate: str
    claims_evaluated: int
    claims_supported: int
    claims_contradicted: int
    claims_refuted: int
    suggested_tasks: list[str] = Field(default_factory=list)
```

---

### Step 5.2: Verification Prompts (`src/argus/verifier/prompts.py`)

Prompts instructing the Expert Verifier:
* Analyze all candidate claims sharing the same `(subject_entity, predicate)`.
* Inspect all associated `Evidence` passages, source URLs, and publication dates.
* Detect if conflicting values represent a temporal progression (e.g. past vs present manager) or a true contradiction.
* Assign final `ClaimStatus` and calibrated `confidence` scores.
* If a contradiction remains unresolved, formulate a precise research subtask to locate definitive ground truth.

---

### Step 5.3: Expert Verifier Engine (`src/argus/verifier/engine.py`)

The verification coordinator:
1. **Target Identification:**
   * Given an `objective_id` (or specific `subject_entity_id`), fetch all `PENDING` claims from `ArgusRepository`.
   * Group claims by `(subject_entity_id, predicate)`.
2. **Adjudication Execution:**
   * For each group:
     * Retrieve all linked `Evidence` objects for each claim in the group.
     * If single claim with high-quality source: adjudicate directly or corroborate with existing knowledge.
     * If multiple claims with identical `object_value`: aggregate evidence IDs and corroborate (`SUPPORTED`).
     * If multiple claims with conflicting `object_value`: call `LLMProvider.generate_structured(..., AdjudicationPayload)` using the expert reasoning model.
3. **Persistence & Auditing:**
   * Update each `Claim` in `ArgusRepository`:
     * Set `claim.status` to `evaluation.status`.
     * Set `claim.confidence` to `evaluation.confidence`.
     * Update `updated_at`.
   * Emit audit events:
     * If contradiction found: `EventType.CONTRADICTION_DETECTED` with conflict details.
     * Emit `EventType.VERIFICATION_COMPLETED`.
4. **Return Value:**
   * Return `list[AdjudicationResult]` summarizing updated claims and any suggested disambiguation tasks.

---

## 4. Test Strategy (`tests/test_verifier.py`)

The test suite must verify the following scenarios offline:

1. **`test_verifier_corroborates_agreeing_claims`:**
   * Two independent claims state the same facility address from different sources.
   * Verifier transitions claims to `SUPPORTED` and aggregates evidence.
2. **`test_verifier_resolves_temporal_supersession`:**
   * Older claim from 2022 says "John Doe" is Plant Manager; newer claim from 2026 says "Jane Smith" is Plant Manager.
   * Verifier updates 2026 claim to `SUPPORTED` and 2022 claim to `REFUTED` with temporal explanation.
3. **`test_verifier_flags_active_contradiction`:**
   * Two simultaneous conflicting sources report different values for the same attribute with no obvious temporal resolution.
   * Verifier marks claims `CONTRADICTED`, emits `CONTRADICTION_DETECTED` audit event, and returns a suggested disambiguation task.
4. **`test_verifier_handles_insufficient_single_source`:**
   * Single low-confidence claim without secondary source corroboration is marked `UNVERIFIED`.

---

## 5. Verification Commands

Once implemented, run:

```bash
uv run ruff check --fix . && uv run ruff format . && uv run pytest -v
```

All unit tests across Phases 0–5 must pass.
