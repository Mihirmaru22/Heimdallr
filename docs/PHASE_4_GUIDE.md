# Phase 4 Implementation Guide: Worker Engine & Extraction Layer

Welcome to **Phase 4** of Argus!

In this phase, you are building the **Worker Engine and Fast Decision Layer**. 
By the end of Phase 4, Argus will be able to take crawled web documents, evaluate their relevance against research objectives, extract structured entities and claims with verbatim evidence quotes, resolve entities against the existing epistemic graph, and persist the verified knowledge into SQLite.

---

## 1. Architectural Principles (From the Brief)

1. **Model Specialization $\neq$ Agent Multiplication (Brief Sec 11):**
   * Workers are task execution engines, not separate autonomous conversational agents.
   * High-volume micro-decisions (*"Is this relevant?"*, *"What are the entities?"*, *"Is entity X same as entity Y?"*) are executed with structured LLM calls (e.g. DeepSeek V4 Flash / OpenRouter) returning strongly typed schemas.
2. **Epistemic Grounding (Brief Sec 10):**
   * No hallucinations or unattributed claims.
   * Every extracted claim must reference an `Evidence` object containing:
     * `url`: Web address of origin.
     * `source_id`: Document content hash (`document.content_hash`).
     * `passage`: Exact verbatim text snippet from the document.
     * `confidence`: Extraction confidence score (0.0 to 1.0).
3. **Relevance Triage Guardrail:**
   * Documents that do not contain substantive information regarding the research task are filtered out immediately, saving downstream extraction and verification tokens.
4. **Entity Resolution:**
   * When extracting an entity, Argus checks existing entities in `ArgusRepository` by canonical name and aliases before creating a new entity record, preventing knowledge graph fragmentation.
5. **Deterministic Testing:**
   * An abstract `LLMProvider` interface allows testing the entire worker pipeline offline with `MockLLMProvider` without network calls or API token costs.

---

## 2. Directory Structure for Phase 4

```text
Argus/
├── docs/
│   ├── PHASE_0_GUIDE.md
│   ├── PHASE_1_GUIDE.md
│   ├── PHASE_2_GUIDE.md
│   ├── PHASE_3_GUIDE.md
│   └── PHASE_4_GUIDE.md          <-- NEW: Phase 4 Guide
├── src/
│   └── argus/
│       ├── core/
│       ├── domain/
│       ├── storage/
│       ├── search/
│       ├── crawler/
│       ├── llm/                  <-- NEW: Structured LLM Provider Layer
│       │   ├── __init__.py
│       │   ├── provider.py       <-- LLMProvider (Abstract Base Class)
│       │   ├── openrouter.py     <-- OpenRouter / OpenAI-compatible JSON client
│       │   └── mock.py           <-- MockLLMProvider (Deterministic offline testing)
│       └── worker/               <-- NEW: Worker Engine & Extraction
│           ├── __init__.py
│           ├── models.py         <-- Extraction schemas & Pydantic models
│           ├── prompts.py        <-- Extraction & relevance prompts
│           └── engine.py         <-- WorkerEngine (Triage, Extraction, Resolution, Persistence)
└── tests/
    ├── test_crawler.py
    ├── test_search.py
    ├── test_storage.py
    ├── ...
    └── test_worker.py            <-- NEW: Worker Engine Test Suite
```

---

## 3. Step-by-Step Code Specifications

### Step 4.1: LLM Provider Abstraction (`src/argus/llm/`)

Argus requires structured responses conforming to Pydantic models. We build an abstract client with an OpenRouter implementation and a Mock provider for unit tests.

#### `src/argus/llm/provider.py`
```python
from abc import ABC, abstractmethod
from typing import TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMProvider(ABC):
    """Abstract interface for LLM calls enforcing structured Pydantic outputs."""

    @abstractmethod
    async def generate_structured(
        self,
        prompt: str,
        response_model: type[T],
        system_prompt: str | None = None,
        temperature: float = 0.0,
    ) -> T:
        """Call LLM and parse the response strictly into the requested Pydantic model."""
        pass
```

#### `src/argus/llm/openrouter.py`
* Implements `LLMProvider` using `httpx.AsyncClient`.
* Targets `https://openrouter.ai/api/v1/chat/completions` (or custom base URL).
* Uses `response_format={"type": "json_object"}` and injects JSON schema instructions into the prompt.
* Parses and validates JSON into `response_model`.

#### `src/argus/llm/mock.py`
* Implements `LLMProvider` returning queued or predefined Pydantic responses.
* Tracks all call inputs (`prompts`, `response_models`) for test assertions.

---

### Step 4.2: Extraction Schemas (`src/argus/worker/models.py`)

These Pydantic models define the structured output contract for the Worker LLM.

```python
from typing import Any
from pydantic import BaseModel, Field


class RelevanceAssessment(BaseModel):
    """Initial assessment of whether a document contains information relevant to the task."""

    is_relevant: bool = Field(
        ..., description="True if document provides facts answering the task"
    )
    reasoning: str = Field(
        ..., description="Brief explanation of relevance determination"
    )
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Confidence in assessment"
    )


class ExtractedEntityItem(BaseModel):
    """Candidate entity identified in the text."""

    name: str = Field(..., min_length=1, description="Primary name of the entity")
    entity_type: str = Field(
        ..., min_length=1, description="Type (e.g. company, facility, person)"
    )
    aliases: list[str] = Field(
        default_factory=list, description="Alternative names or abbreviations"
    )
    attributes: dict[str, Any] = Field(
        default_factory=dict, description="Attributes discovered"
    )


class ExtractedClaimItem(BaseModel):
    """Candidate factual claim with supporting quotation."""

    subject_name: str = Field(
        ..., min_length=1, description="Name of the subject entity"
    )
    predicate: str = Field(
        ..., min_length=1, description="Relation (e.g. HAS_PLANT_MANAGER, LOCATED_IN)"
    )
    object_value: str = Field(..., min_length=1, description="Value or target name")
    verbatim_passage: str = Field(
        ..., min_length=1, description="Exact quotation from text supporting claim"
    )
    confidence: float = Field(
        default=0.8, ge=0.0, le=1.0, description="Estimated confidence score"
    )


class ExtractionPayload(BaseModel):
    """Unified extraction result returned by Worker LLM."""

    relevance: RelevanceAssessment
    entities: list[ExtractedEntityItem] = Field(default_factory=list)
    claims: list[ExtractedClaimItem] = Field(default_factory=list)
    suggested_followup_tasks: list[str] = Field(default_factory=list)
```

---

### Step 4.3: Extraction Prompts (`src/argus/worker/prompts.py`)

System and user prompt templates instructing the LLM:
* Enforce strict epistemic honesty: **do not invent facts**.
* Quotations in `verbatim_passage` must be direct substrings from the provided document.
* Predicates must be standardized uppercase identifiers (`OPERATES`, `LOCATED_IN`, `HAS_LEADERSHIP`, `PRODUCES`).

---

### Step 4.4: Worker Engine (`src/argus/worker/engine.py`)

The core execution coordinator:
1. **Input:** `Document`, `ResearchTask`, `ResearchObjective`.
2. **Execution:**
   * Calls `LLMProvider.generate_structured(..., ExtractionPayload)`.
   * If `not payload.relevance.is_relevant`:
     * Logs `ResearchEvent(EventType.TASK_PROGRESSED)` noting document was examined and deemed irrelevant.
     * Returns early with empty results.
   * If relevant:
     * **Entity Resolution:**
       * For each `ExtractedEntityItem`, check `ArgusRepository.list_entities(...)` for an existing entity matching `name` (case-insensitive) or in `aliases`.
       * If found, update aliases/attributes on existing `Entity`.
       * If not found, create new `Entity` and persist via `save_entity`.
     * **Evidence Grounding:**
       * For each `ExtractedClaimItem`, verify `verbatim_passage` exists in `document.text_content`.
       * Create `Evidence(source_id=document.content_hash, url=document.url, passage=verbatim_passage, confidence=item.confidence)`.
       * Persist `Evidence` via `save_evidence`.
     * **Claim Generation:**
       * Resolve `subject_entity_id` to the subject entity ID.
       * Resolve `object_entity_id` if the object matches a known entity.
       * Create `Claim(subject_entity_id=..., predicate=item.predicate, object_value=item.object_value, evidence_ids=[evidence.evidence_id], confidence=item.confidence)`.
       * Persist `Claim` via `save_claim`.
     * **Audit:**
       * Emit `ResearchEvent(EventType.EVIDENCE_COLLECTED, details=...)`.
       * Return summary of created entities, evidence, and claims.

---

## 4. Test Strategy (`tests/test_worker.py`)

The test suite must verify all key behaviors without internet access:

1. **`test_mock_llm_provider`:** Verifies mock returns typed models and records prompts.
2. **`test_worker_handles_irrelevant_document`:** An off-topic document is flagged irrelevant, yielding 0 entities/claims and recording the audit log.
3. **`test_worker_extracts_entities_and_grounded_claims`:** Relevant text creates `Entity`, `Evidence` with matching document hash, and `Claim` linking both.
4. **`test_worker_resolves_existing_entities`:** If "Ford Motor Co." already exists, a mention of "Ford" with alias updates the existing entity rather than duplicating it.
5. **`test_worker_verbatim_quote_validation`:** Ensures extracted evidence quotes correlate to text present in the document.

---

## 5. Verification Commands

Once implemented, run:

```bash
uv run ruff check --fix . && uv run ruff format . && uv run pytest -v
```

All tests across Phases 0–4 must pass.
