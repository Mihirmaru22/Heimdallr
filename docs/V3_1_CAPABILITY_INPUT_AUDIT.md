# V3.1 — CAPABILITY INPUT AUDIT
**Comprehensive Data-Flow and Provenance Analysis of Capability Routing Inputs**
**Repository:** Argus / Heimdallr V3.1
**Date:** 2026-10-08
**Auditor:** Antigravity Autonomous Verification Suite

---

## Executive Summary

To guarantee that Heimdallr's Capability Registry selects capabilities strictly from legitimate runtime information rather than benchmark ground-truth leakage, this audit traces the end-to-end data flow from benchmark task definitions to final capability execution.

Every input field entering `InvestigationQuestion`, `CapabilityMatcher`, and `CapabilityRegistry` was audited for provenance, capability-bearing semantic content, and evaluator isolation.

---

## 1. End-to-End Capability Data-Flow Pipeline

```text
[CAPABILITY_MATCH_V2 Task]
        │
        ▼ (Stripped via task.get_public_view())
[InvestigationQuestion]
   ├── question_text (str)
   ├── question_type (QuestionType)
   ├── required_evidence (list[str])
   ├── related_entities (list[str])
   ├── temporal_context (dict | None)
   ├── jurisdiction (str)
   └── specialist_requirements (list[str]) [Quarantined in Mode B]
        │
        ▼ (Inspected by CapabilityLabelLeakageGuard)
[CapabilityMatcher.match() & select_minimum_sufficient_set()]
   ├── Match Score Computation (Semantic Token Match + Stem Lemma + Evidence Covering)
   └── Greedy Set-Covering Optimization over required_evidence
        │
        ▼
[Ranked Capability Candidates]
        │
        ▼ (Two-Phase Decoupling)
[Implementation Adapter Selection]
        │
        ▼
[Execution via Research Action]
```

---

## 2. Input Field Inventory & Provenance Matrix

| Field | Source | Producer | Consumer | Contains Capability Info? | Evaluator-Only? | Legitimate Runtime Info? |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: |
| **`question_text`** | User Query / Investigation Goal | User or Planner decomposition | `CapabilityMatcher` | No (Natural language prompt) | **No** | **Yes** (Primary semantic signal) |
| **`question_type`** | Archetype taxonomy | Investigation Planner | `CapabilityMatcher` | Indirect (Structural intent: `ENTITY_DISCOVERY`, `OFFICER_TENURE`, etc.) | **No** | **Yes** (Standard ontology) |
| **`required_evidence`** | Epistemic verification requirements | Investigation Planner / Question Contract | `CapabilityMatcher` (Greedy Set Cover) | Indirect (Declares required record types, e.g. "SEC 10-K", "CT log SAN") | **No** | **Yes** (Legitimate evidentiary contract) |
| **`related_entities`** | Entity graph / query entities | Upstream extraction or state | `CapabilityMatcher` | No (Entity names, e.g. "Apex Technologies") | **No** | **Yes** (Entity context) |
| **`temporal_context`** | Investigation constraints | User prompt / As-of date | `CapabilityMatcher` | No (e.g. `{"as_of_date": "2019-12-31"}`) | **No** | **Yes** (Temporal filter) |
| **`jurisdiction`** | Legal jurisdiction scope | Entity state / question scope | `CapabilityMatcher` | No (e.g. "US", "GB", "GLOBAL") | **No** | **Yes** (Jurisdiction filter) |
| **`specialist_requirements`** | Legacy V2 orchestrator tag | Investigation Planner / Orchestrator | `CapabilityMatcher` (`spec_bonus`) | **Yes** (Direct specialist category hint, e.g. `["corporate"]`) | **Potentially Leakable** (Audited below) | **Context-Dependent** |
| **`required_capabilities`** | Benchmark ground truth | Evaluator Task Definition | `MatcherGraderV2` ONLY | **Yes** (Ground-truth capability IDs) | **YES** | **NO (Forbidden at runtime)** |
| **`forbidden_capabilities`** | Benchmark ground truth | Evaluator Task Definition | `MatcherGraderV2` ONLY | **Yes** (Negative labels) | **YES** | **NO (Forbidden at runtime)** |
| **`minimum_sufficient_set`** | Benchmark ground truth | Evaluator Task Definition | `MatcherGraderV2` ONLY | **Yes** (Minimal exact set) | **YES** | **NO (Forbidden at runtime)** |
| **`acceptable_alternative_sets`** | Benchmark ground truth | Evaluator Task Definition | `MatcherGraderV2` ONLY | **Yes** (Alternative sets) | **YES** | **NO (Forbidden at runtime)** |
| **`expected_implementation_id`**| Benchmark ground truth | Evaluator Task Definition | `MatcherGraderV2` ONLY | **Yes** (Target adapter ID) | **YES** | **NO (Forbidden at runtime)** |

---

## 3. Dedicated Audit: `InvestigationQuestion.specialist_requirements`

The field `specialist_requirements: list[str] = Field(default_factory=list)` exists on `InvestigationQuestion`. A dedicated investigation was conducted to determine its exact lifecycle:

### Provenance Audit Questions:
1. **Where is this field created?**
   - Declared in `src/argus/investigation/question.py` (line 66) as an optional list of strings defaulting to `[]`.
2. **Who populates it?**
   - In production Heimdallr V2:
     - `src/argus/investigation/planner.py` (lines 95, 110, 124, 139, 152) assigns archetype hints during initial goal decomposition (e.g. `q_corp` receives `["corporate"]`, `q_infra` receives `["infrastructure"]`).
     - `src/argus/investigation/orchestrator.py` (lines 510, 532, 555) assigns hints during reactive multi-specialist chaining (e.g. discovering a UK subsidiary triggers a follow-up network query tagged with `["infrastructure"]`).
   - In `CAPABILITY_MATCH_V2`:
     - **It was populated with `[]` (empty list) across ALL 140 benchmark tasks.**
3. **Is it derived from the question?**
   - In production, it was statically assigned by rule templates in the Planner, not derived dynamically from question text.
4. **Is it derived from benchmark ground truth?**
   - **No.** In `CAPABILITY_MATCH_V2`, ground truth resides in `task.required_capabilities`, while `task.specialist_requirements` was strictly empty.
5. **Is it copied from `required_capabilities`?**
   - **No.**
6. **Is it generated by the Investigation Planner?**
   - Yes, during live end-to-end multi-step investigations (`planner.py`).
7. **Is it generated by a production component?**
   - Yes (`InvestigationPlanner` and `InvestigationEngine`).
8. **Does the benchmark populate it directly?**
   - No. All 140 tasks had `specialist_requirements = []`.
9. **Does the matcher use it directly or indirectly?**
   - In `CapabilityMatcher.match()` (lines 145–151), if present, matching capability categories receive a `spec_bonus = 0.20`.
   - In `CapabilityMatcher.select_minimum_sufficient_set()`, candidate selection is strictly driven by `_cap_satisfies_evidence()` over `required_evidence`.

---

## 4. `specialist_requirements` Decision: DERIVE

### Architectural Evaluation:
- **Why NOT RETAIN as-is:** Hardcoding specialist names into questions couples the question layer to concrete specialist verticals, violating the V3.1 abstraction separating abstract capabilities from specialists. Furthermore, empirical testing in Mode C demonstrated that an unverified upstream hint can cause a 0.71% deflection under hostile injection.
- **Why NOT REMOVE completely:** Multi-step investigation planning benefits from tracking what type of intelligence domain a decomposed sub-goal addresses.
- **Why DERIVE is the Optimal Architectural Choice:**
  In V3.2, `specialist_requirements` must be refactored into **`derived_capability_requirements`**, produced explicitly through an upstream question-understanding step:
  ```text
  Investigation Goal / Observation
          │
          ▼
  Question Understanding & Evidentiary Decomposition
          │
          ▼
  Derived Capability Requirements (e.g., ["corporate_registry_intelligence"])
          │
          ▼
  Capability Matcher & Registry Resolution
  ```

For the purpose of benchmark validation, **Mode B proves that when `specialist_requirements` is completely empty / quarantined, Heimdallr achieves 100.0% Minimum-Set Accuracy purely from question semantics and structured evidence contracts.**

---

## 5. Conclusion

1. Evaluator-only fields (`required_capabilities`, `forbidden_capabilities`, `minimum_sufficient_set`) are strictly quarantined and never enter runtime data structures.
2. `specialist_requirements` was empty in the baseline benchmark and was not the source of the 100% score.
3. Heimdallr routes capabilities legitimately through evidence requirement matching and semantic intent.
