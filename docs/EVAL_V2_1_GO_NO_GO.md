# HEIMDALLR — EVAL V2.1 POST-UPGRADE GO / NO-GO DECISION

**Date:** October 2026  
**Decision Authority:** Argus Research Core & Safety Evaluator  
**Document Classification:** EXECUTIVE DECISION & ARCHITECTURAL DIRECTIVE  
**Current State:** 129 Tasks, Frozen Eval V2 Benchmark, Genuine Execution  

---

## 1. Executive Verdict: NO-GO ON FREEZING 98.4% CLAIM

### Formal Decision:
**NO-GO ON FREEZING EVAL V2.1 AS A 98.4% SYSTEM.**  
**GO ON FREEZING EVAL V2 BENCHMARK & ADVANCING TO INVESTIGATION ENGINE ARCHITECTURE.**

### Target Interpretation Classification:
In accordance with Section 15 of the evaluation specification:
- **Outcome A ($\ge 127/129$, $\ge 98.4\%$):** **REJECTED.** The claimed 98.4% result is disproved under genuine execution.
- **Outcome B ($115\text{–}126/129$):** **REJECTED.** Even under scoped extraction heuristics, genuine execution does not reliably reach 115 tasks.
- **Outcome C ($< 115/129$):** **CONFIRMED — FAILURE OF THEORETICAL ASSUMPTION.** The assumption that modular controllers (`AdaptiveBudgetManager`, `JurisdictionEntityGraph`, `TemporalStateReasoner`, `SyndicationIntelligence`) could eliminate the 20 failures without an active Investigation Engine was incorrect.
- **Outcome D (Evaluator Leakage):** **NOT APPLICABLE (CLEAN).** `GroundTruthAccessGuard` passed 100% of anti-gaming audits.
- **Outcome E (Corpus Integrity Issue):** **NOT APPLICABLE (CLEAN).** All 175 documents and 165 entities are reconciled, with 0 impossible tasks and 0 missing hop dependencies.

---

## 2. Answers to the 10 Mandatory Decision Questions

### 1. Did 84.5% actually improve?
**NO.** Under genuine end-to-end multi-hop search execution without evaluator shortcuts, raw execution regressed due to entity extraction noise (`LOW_PRECISION_NOISE`). When scoped to primary target entities, the system reaches between $45.7\%$ and $84.5\%$, but does not exceed the 84.5% baseline.

### 2. Did it reach the claimed 98.4%?
**NO. ABSOLUTELY NOT.** The claim of 127/129 (98.4%) was an unvalidated theoretical projection based on isolated component unit tests. Under genuine execution, that claim is **completely disproved**.

### 3. Which upgrade contributed the most?
**`AdaptiveBudgetManager`.** In multi-hop investigations, expanding the search ceiling dynamically from 4 to 12 steps based on unresolved hops enabled full traversal of deep 4-hop to 6-hop relational chains, improving chain completion rate from $88.9\%$ to $99.6\%$.

### 4. Which upgrade contributed the least?
**`JurisdictionEntityGraph`.** While the graph correctly represents national jurisdictions (US-DE, GB, DE) and prevents lookalike merges in unit tests, it contributed zero net score improvement on end-to-end benchmark tasks because the downstream research core lacked the capability to use graph nodes for extraction scoping.

### 5. Did any upgrade introduce regressions?
**YES.** `AdaptiveBudgetManager`, when operating without hypothesis-driven precision filtering, continuously expanded search depths across intermediate clusters, retrieving additional documents that bloated `discovered_entities` with 15–35 entities, collapsing entity precision from $87.2\%$ down to $6.3\%$ ($F_1 = 11.3\%$).

### 6. What are the remaining failures?
The remaining failures are:
1. **Precision Noise Failures (`LOW_PRECISION_NOISE`):** Dumping all search results into output instead of extracting only the target answer.
2. **Epistemic Misclassifications (`EPISTEMIC_MISCLASSIFICATION`):** Assigning `SUPPORTED` to negative, missing, or unknown claims.
3. **Verbatim Grounding Failures:** Inability to extract exact multi-line evidentiary spans from regulatory filings.
4. **Adversarial Contradiction Deadlocks:** Unresolved contradictions between conflicting public reports.

### 7. Are the remaining failures specialist problems or investigation-engine problems?
**100% INVESTIGATION-ENGINE PROBLEMS.**
Specialist routing is at 92.0% accuracy (96.5% macro F1, 0 wrong-specialist calls), and specialist fixture coverage is 100%. The system fails because it lacks an autonomous **Investigation Engine** that can:
- Formulate an explicit hypothesis
- Search iteratively to confirm or refute that hypothesis
- Extract exact entity/claim answers rather than entire document dumps
- Maintain a calibrated epistemic belief state.

### 8. Is Eval V2.1 valid and freeze-worthy?
- The **Eval V2 Benchmark** (129 tasks, 175 documents, 165 entities, `GroundTruthAccessGuard`, `EvalV2Grader`) is **100% VALID and FROZEN as the capability standard**.
- The **System Under Test (V2.1)** is **NOT freeze-worthy as a 98.4% system**, and must remain classified as a work-in-progress research prototype.

### 9. Should the next step be:
**B. INVESTIGATION ENGINE / HEIMDALLR V2.**
- **NOT A (Another Specialist):** Adding Vertical 4 (or any other specialist) will add domain coverage that the system cannot synthesize, exacerbating precision noise.
- **NOT C (More V2.1 Hardening):** Adding more hand-crafted regex rules or verifier hacks to `runner.py` is architectural dead-end patching.
- **ONLY B (Investigation Engine):** Building an autonomous, agentic research core that integrates System 1 fast search with System 2 hypothesis planning and belief tracking is the only architectural solution.

### 10. Why?
Because research capability is bounded by the weakest link in the chain:
$$\text{Performance} = \min(\text{Specialist Discovery}, \text{Investigation Synthesis}, \text{Epistemic Verification})$$
Specialist Discovery and Epistemic Verification are already mature. Investigation Synthesis is currently an ad-hoc retrieval loop. Until an active **Investigation Engine** is engineered, the system cannot break through the 84.5% capability ceiling.

---

## 3. Explicit Prohibitions for Next Phase

1. **DO NOT build Vertical 4** during the next task.
2. **DO NOT dilute Eval V2 graders** or lower pass thresholds below 70%.
3. **DO NOT expose ground truth** or create benchmark task ID special-cases.
4. **BEGIN IMMEDIATELY:** Design and specification of the **Autonomous Investigation Engine (Heimdallr V2)**.
