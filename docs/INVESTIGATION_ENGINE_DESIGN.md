# HEIMDALLR V2 — INVESTIGATION ENGINE DESIGN SPECIFICATION
## From Evidence-Backed Researcher → Persistent Autonomous Investigation System

---

### Executive Summary

Heimdallr V1 established an evidence-backed research pipeline capable of crawling, document intelligence, claim extraction, evidence alignment, specialist invocation, and epistemic verification. However, capability evaluations revealed a fundamental architectural bottleneck:

> **The Research Sprawl Paradox:** Increasing research budget produced more queries, more retrieved pages, and more candidate entities, but dilutes precision. The system lacked an explicit epistemic model of what it was attempting to establish, what remained unresolved, what concrete evidence was required, which action promised the highest information gain, and when evidence was sufficient to stop.

Heimdallr V2 shifts the foundational paradigm from:
```
OBJECTIVE → SEARCH → DOCUMENT → CLAIM → VERIFICATION
```
to a structured, hypothesis-driven, state-retaining investigation engine:
```
OBJECTIVE
   ↓
INVESTIGATION STATE
   ↓
QUESTIONS / HYPOTHESES
   ↓
EVIDENCE REQUIREMENTS
   ↓
RESEARCH ACTION
   ↓
OBSERVATION
   ↓
CLAIM & VERIFICATION
   ↓
STATE & BELIEF UPDATE
   ↓
NEXT QUESTION / HYPOTHESIS
   ↓
STOP / CONTINUE DECISION
   ↓
SYNTHESIS & DOSSIER GENERATION
```

---

### Core Architectural Principles

1. **Structured Investigation over Generic Agent Loops:**
   The engine does not execute an open-ended "while True: think()" loop. It evaluates explicit question graphs, tests symmetrical hypotheses (requiring evidence both *for* and *against*), and executes prioritized actions chosen by expected information yield.

2. **First-Class Investigation State (`InvestigationState`):**
   State is fully serializable, checkpointed after every cycle, and append-only in its audit trail. Crashes and interruptions are recoverable with deterministic reconstruction.

3. **Evidence Requirements as Research Gatekeepers:**
   Before any query or fetch action is dispatched, explicit evidentiary conditions are defined (e.g. primary registry filing, Certificate Transparency log, SEC Exhibit 21 schedule). Research actions are evaluated by whether they satisfy active evidence requirements, eliminating irrelevant crawler sprawl.

4. **Multi-Specialist Chaining without Human Intervention:**
   Specialists are preserved with strict epistemic boundaries (Clean-room IdentityProbeSpecialist, Native InfrastructureProbeSpecialist, Clean-room CorporateProbeSpecialist). One specialist's discovery directly generates questions that activate another (e.g., Corporate subsidiary discovery → Infrastructure SAN enumeration → Identity CISO probe → Corporate officer appointment verification).

5. **First-Class Stopping Taxonomy:**
   Stopping is never delegated to subjective LLM self-assessment ("LLM thinks it is done"). Stopping is governed by strict deterministic criteria:
   - `OBJECTIVE_SATISFIED`: All objective-derived questions resolved.
   - `SUFFICIENT_EVIDENCE`: Critical questions resolved and satisfaction threshold met.
   - `NO_INFORMATION_GAIN`: Plateau detected after consecutive zero-gain actions.
   - `BUDGET_EXHAUSTED_WITH_ACCEPTABLE_COVERAGE`: Step limit reached with high resolution.
   - `BUDGET_EXHAUSTED_WITH_CRITICAL_MISSING_FIELDS`: Step limit reached with unresolved critical gaps.
   - `UNRESOLVABLE_CONTRADICTION`: Irreconcilable contradictory evidence.
   - `SAFETY_STOP`: Adversarial or structural stop triggered.

6. **Rigorous Epistemic Calibration:**
   Distinguishes:
   - `SUPPORTED`: Proven by authoritative primary evidence.
   - `INFERRED`: Derived via probabilistic or topological reasoning.
   - `UNKNOWN`: Insufficient evidence to substantiate or refute.
   - `NOT_FOUND`: Exhaustive investigation proved non-existence or non-disclosure.
   - `CONTRADICTED`: Refuted by superseding authority or adversarial indicator.

---

### Key Subsystems

| Subsystem | Module | Core Responsibilities |
| :--- | :--- | :--- |
| **Investigation State** | [state.py](file:///data/shared/project/PlayGround/Argus/src/argus/investigation/state.py) | Full epistemic knowledge graph, question topology, active/completed branches, audit trail, budget telemetry. |
| **Question Topology** | [question.py](file:///data/shared/project/PlayGround/Argus/src/argus/investigation/question.py) | Parent/child question generation, dependency blocking, status transitions, grounding links. |
| **Hypothesis Model** | [hypothesis.py](file:///data/shared/project/PlayGround/Argus/src/argus/investigation/hypothesis.py) | Testable propositions, symmetrical evidence tracking (supporting vs contradicting), confidence calibration. |
| **Evidence Requirements** | [evidence.py](file:///data/shared/project/PlayGround/Argus/src/argus/investigation/evidence.py) | Mandatory source-type constraints, independent corroboration standards, temporal bounds. |
| **Action Model** | [action.py](file:///data/shared/project/PlayGround/Argus/src/argus/investigation/action.py) | Strongly typed research actions, rationale, specialist target, expected information gain. |
| **Branch Management** | [branch.py](file:///data/shared/project/PlayGround/Argus/src/argus/investigation/branch.py) | Isolated exploration trees, step/cost budgets, branch completion and abandonment. |
| **Information Gain** | [information_gain.py](file:///data/shared/project/PlayGround/Argus/src/argus/investigation/information_gain.py) | Heuristic utility estimator ranking actions by relevance, unresolved need, and marginal cost. |
| **Stopping Policy** | [stopping.py](file:///data/shared/project/PlayGround/Argus/src/argus/investigation/stopping.py) | Deterministic evaluation of termination criteria across the formal stop taxonomy. |
| **Persistence Store** | [store.py](file:///data/shared/project/PlayGround/Argus/src/argus/investigation/store.py) | Checkpointing to JSON state files, append-only JSONL audit streams, crash recovery. |
| **Investigation Planner** | [planner.py](file:///data/shared/project/PlayGround/Argus/src/argus/investigation/planner.py) | Objective decomposition, question graph compilation, action selection, contradiction question generation. |
| **Orchestrator** | [orchestrator.py](file:///data/shared/project/PlayGround/Argus/src/argus/investigation/orchestrator.py) | Execution loop, specialist dispatch, observation processing, belief updates, multi-specialist chaining. |

---

### Symmetrical Scrutiny & Contradiction-Driven Research

When contradictory claims arise between sources (e.g. Form 10-K from 2020 listing Donald Vance as SVP AI vs current reports listing David Marcus), the system refuses to arbitrarily pick one. Instead:
1. It instantiates a formal `contradiction` record.
2. The Planner generates a targeted contradiction question:
   *"Resolve contradictory claims regarding Head of AI: Donald Vance vs David Marcus. Which executive is currently authoritative?"*
3. The engine creates an action seeking authoritative restatements (e.g. Form 10-K/A amendment).
4. Evidence resolves the conflict with temporal precision: David Marcus succeeded Donald Vance effective January 15, 2022. Donald Vance is marked historical/resigned; David Marcus is marked active.

---

### Distinguishing UNKNOWN from NOT_FOUND

A major flaw of legacy search loops is hallucinating contacts or confusing "not found" with "unknown".
Heimdallr V2 enforces strict boundaries:
- **`NOT_FOUND`:** Official records exist and were examined, but the specific attribute is confirmed non-existent (e.g. "Vice President of Quantum Cryptocurrency" does not exist in the 10-K schedule) or undisclosed (e.g. Elena Rostova's business contact is explicitly stated as "Not available via public web portal").
- **`UNKNOWN`:** The attribute may exist, but search was unable to access authoritative disclosures.
- **Strict Anti-Hallucination:** Under zero circumstances does the engine invent email addresses or executive credentials.
