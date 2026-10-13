# HEIMDALLR V3: P0.3-GR FAILURE PATH & ROOT CAUSE ANALYSIS
## SYSTEMIC REASONING AUDIT OF GENERALIZATION & LIVE-WEB BENCHMARKS

**Milestone:** P0.3-GR (Generalization Reasoning Remediation)  
**Date:** 2026-10-13  
**Auditor:** Senior AI Systems Architect, Research-Engine Engineer, Evaluation Scientist, and Security Auditor  
**Baseline Evaluated:** Generalization Benchmark V2 (100 tasks) & Controlled Live-Web V1 (30 tasks)  

---

### 1. AUDIT METHODOLOGY & SUMMARY OF ROOT CAUSES

A line-by-line trace of the research engine execution path was conducted across `src/argus/investigation/orchestrator.py`, `planner.py`, `state.py`, and `stopping.py`. The trace confirmed three systemic architectural flaws in the production reasoning pipeline:

1. **Absence of Cross-Document Claim Reconciliation (Causing `CONTRADICTION_MISSED`):**
   - In `orchestrator.py` (lines 796–806 & 1201–1224), contradiction detection was implemented solely as an intra-sentence keyword search for explicit conflict tokens (`"contradict"`, `"conflict"`, `"dispute"`, `"differing"`).
   - In real-world and benchmark tasks where Doc A asserts a metric (e.g. 600 kg payload) and Doc B asserts a conflicting metric (e.g. 450 kg ISO limit), neither document contains conflict words.
   - The engine extracted both assertions as independently `SUPPORTED` claims without performing cross-document attribute comparison, leaving `state.contradictions` empty and defaulting to `SUPPORTED`.

2. **Entity & Department Scope Contamination (Causing `INCORRECT_NOT_FOUND`):**
   - In `planner.py` and `orchestrator.py` (lines 858–880 & 1364–1375), target entity matching did not enforce hierarchical or relationship scope.
   - When given a query regarding a non-existent department or subsidiary of a real organization (e.g. *"Kuka Dynamics Department of Anti-Gravity Propulsion"* or *"Zephyr Lunar Technologies LLC"*), the planner matched the parent entity tokens (`Kuka Dynamics` or `Zephyr`).
   - The engine retrieved documents regarding the parent organization, extracted factual claims regarding the parent, and in line 1364 resolved the question as `SUPPORTED` because `new_claims_found > 0` or `len(docs) > 0`.
   - Parent existence was conflated with child/relationship existence.

3. **Epistemic Acceptance of Fragmentary/Unverified Mentions (Causing `INCORRECT_INSUFFICIENT_EVIDENCE`):**
   - In `orchestrator.py` (lines 1364–1375), the question resolution policy prioritized positive document retrieval over epistemic sufficiency: `elif len(docs) > 0: q.resolve(status=QuestionStatus.SUPPORTED)`.
   - Any document mentioning a topic—even if explicitly characterized as an unconfirmed forum rumor, preliminary in-vitro test, unproven algorithm lemma, or weathered illegible inscription—was treated as sufficient proof to resolve questions as `SUPPORTED`.
   - The engine lacked an epistemic sufficiency filter to calibrate evidentiary weight and abstain with `INSUFFICIENT_EVIDENCE`.

---

### 2. DETAILED TRACE OF REPRESENTATIVE FAILED TASKS

| Failure ID | Category | Expected Status | Actual Status | Relevant Evidence Record | First Incorrect Decision | Root Cause | Proposed General-Purpose Remediation | Regression Test Case |
| :--- | :--- | :---: | :---: | :--- | :--- | :--- | :--- | :--- |
| **FAIL-01** (`gen2_task_31`) | CONFLICTING_AMBIGUOUS | `CONTRADICTED` | `SUPPORTED` | `gen2_doc_31_a` (PR claiming 600 kg) vs `gen2_doc_31_b` (TÜV ISO certificate strictly 450 kg) | `orchestrator.py:848`: Both documents extracted as independent `SUPPORTED` claims because neither contains lexical conflict tokens. | No cross-document comparison of numerical attributes for the same subject/property. | Cross-document `ContradictionResolver` extracting normalized numerical attributes and flagging >5% discrepancies between independent sources. | `test_numerical_contradiction_payload` |
| **FAIL-02** (`gen2_task_33`) | CONFLICTING_AMBIGUOUS | `CONTRADICTED` | `SUPPORTED` | `gen2_doc_33_a` (35.2% marketing) vs `gen2_doc_33_b` (Fraunhofer 31.4% certified) | `orchestrator.py:848`: Extracted as two valid claims; no cross-document reconciliation. | Numerical discrepancy (35.2% vs 31.4%) between marketing and lab certification not compared. | Property-based claim grouping matching solar efficiency and detecting value divergence beyond tolerance. | `test_numerical_contradiction_efficiency` |
| **FAIL-03** (`gen2_task_36`) | CONFLICTING_AMBIGUOUS | `CONTRADICTED` | `SUPPORTED` | `gen2_doc_36_a` (Clean Energy Blog claiming LFP) vs `gen2_doc_36_b` (Utility filing proving Sodium-Ion) | `orchestrator.py:848`: Extracted claims with differing chemistry strings as non-conflicting. | Categorical mutual exclusivity (Sodium-Ion vs LFP battery chemistry) not recognized. | Domain-agnostic categorical incompatibility detection for mutually exclusive attributes of the same physical installation. | `test_categorical_contradiction_chemistry` |
| **FAIL-04** (`gen2_task_40`) | CONFLICTING_AMBIGUOUS | `CONTRADICTED` | `SUPPORTED` | `gen2_doc_40_a` (Venture pitch 128 qubits) vs `gen2_doc_40_b` (IEEE paper confirming exactly 64 operational qubits) | `orchestrator.py:848`: Both claims marked `SUPPORTED`. | Numerical contradiction on hardware specifications (128 vs 64) not detected. | Numerical attribute comparison on transmon qubit count. | `test_numerical_contradiction_qubits` |
| **FAIL-05** (`gen2_task_46`) | NEGATIVE_NOT_FOUND | `NOT_FOUND` | `SUPPORTED` | `gen2_doc_01_a` (Kuka Dynamics Munich registry) and `gen2_doc_negative_registry` (official registry confirming department does not exist) | `orchestrator.py:860`: Entity matcher matched parent entity `Kuka Dynamics AG`, extracted claims about Munich HQ, and line 1364 resolved target question as `SUPPORTED`. | Parent-to-child entity contamination. Department absence was masked by parent company presence. | `EntityScopeVerifier` enforcing that child/department entities must be directly supported in evidence, and parent presence does not imply child existence. | `test_negative_department_parent_contamination` |
| **FAIL-06** (`gen2_task_48`) | NEGATIVE_NOT_FOUND | `NOT_FOUND` | `SUPPORTED` | Query for fictitious entity `Zephyr Lunar Technologies LLC`. Corpus contains `Zephyr Microgrid Systems`. | `planner.py`: Planner searched for token `Zephyr`, retrieved `Zephyr Microgrid Systems` docs, and line 1370 resolved question as `SUPPORTED`. | Entity token overlap mistaken for target entity verification. | Strict entity boundary and full-name verification; if search across relevant domain registries yields no match, return `NOT_FOUND`. | `test_negative_fictitious_entity_absence` |
| **FAIL-07** (`gen2_task_47`) | INSUFFICIENT_EVIDENCE | `INSUFFICIENT_EVIDENCE` | `SUPPORTED` | `gen2_doc_47_insuff_room_temp` (Preliminary resistivity drop at 294 K; unmeasurable susceptibility; replication failed; inconclusive) | `orchestrator.py:848`: Extracted sentence *"A single four-probe resistivity drop was observed"* as `SUPPORTED` claim; line 1364 resolved question as `SUPPORTED`. | Failure to evaluate evidentiary sufficiency; preliminary in-vitro / exploratory observations treated as confirmed proof. | `EpistemicSufficiencyEvaluator` identifying preliminary / unconfirmed / inconclusive indicators and setting `INSUFFICIENT_EVIDENCE`. | `test_epistemic_abstention_preliminary_findings` |
| **FAIL-08** (`gen2_task_49`) | INSUFFICIENT_EVIDENCE | `INSUFFICIENT_EVIDENCE` | `SUPPORTED` | `gen2_doc_49_insuff_taranis_insider` (Unconfirmed forum chatter regarding employee questioning; zero official reports; completely unverified) | `orchestrator.py:1370`: `elif len(docs) > 0: q.resolve(status=QuestionStatus.SUPPORTED)`. | Unverified single-source rumors accepted as proof merely because a document was retrieved. | Rumor / unverified source discount requiring corroboration and setting `INSUFFICIENT_EVIDENCE`. | `test_epistemic_abstention_unverified_rumor` |
| **FAIL-09** (`live_task_13`) | CONFLICTING_CLAIMS | `CONTRADICTED` | `SUPPORTED` | Web sources asserting Alexander Graham Bell patent vs Antonio Meucci / Elisha Gray priority disputes | `live_web/evaluator.py:94`: Concluded `SUPPORTED` because articles mention Bell without resolving the priority dispute. | Missed historical attribution conflict across competing inventors. | Cross-source entity-relationship conflict detection for single-inventor / sole-credit disputes. | `test_live_web_contradiction_detection` |
| **FAIL-10** (`live_task_16`) | TEMPORAL_CHANGE | `SUPPORTED` | `CONTRADICTED` | Web sources describing Twitter rebranding to X Corp under Elon Musk | `live_web/evaluator.py:87`: Flagged contradiction because both names "Twitter" and "X" appeared in retrieved articles. | False contradiction caused by failure to apply temporal succession reasoning to rebranding. | Integration of `TemporalStateReasoner` to recognize rebranding / succession as `SUPPORTED` temporal change. | `test_live_web_temporal_change_rebranding` |
| **FAIL-11** (`live_task_23`) | NEGATIVE_FINDINGS | `NOT_FOUND` | `SUPPORTED` | Query regarding NASA Warp Drive Starship. Web sources mention NASA and theoretical Alcubierre metrics. | `orchestrator.py:1364`: Found NASA articles and Alcubierre concept, resolved as `SUPPORTED`. | Conflated theoretical paper discussion with active NASA spacecraft program. | Relational scope check verifying operational spacecraft status rather than conceptual paper mentions. | `test_live_web_negative_finding_nonexistent_program` |
| **FAIL-12** (`live_task_28`) | INSUFFICIENT_PUBLIC_EVIDENCE | `INSUFFICIENT_EVIDENCE` | `SUPPORTED` | Query regarding Gemini training cluster internal topology. Web sources discuss general TPU v5p specs. | `orchestrator.py:1370`: Retrieved general TPU articles, resolved as `SUPPORTED`. | Accepted general hardware marketing as answer to proprietary cluster topology query. | Epistemic sufficiency check confirming proprietary/internal architecture details are absent from public documents. | `test_live_web_insufficient_evidence_proprietary` |

---

### 3. REMEDIATION PLAN & ARCHITECTURAL INVARIANTS

To fix these systemic failure modes without overfitting or introducing benchmark-specific logic:

1. **Phase 2: Contradiction Engine (`ContradictionResolver`):**
   - Implement `src/argus/investigation/contradiction_resolver.py`.
   - Structure claims into comparable attributes with normalized numeric values, units, and categories.
   - Detect numeric deviations (>5% variance) and categorical incompatibilities across independent sources.
   - Integrate `TemporalStateReasoner` to differentiate temporal progression (rebranding, tenure succession) from genuine factual disputes.

2. **Phase 3: Entity & Scope Guard (`EntityScopeVerifier`):**
   - Implement hierarchical entity verification: parent existence does not substantiate child entities, departments, or specific relationships.
   - Authoritative negative records or absence across complete domain searches resolve to `NOT_FOUND`.

3. **Phase 4: Epistemic Sufficiency Reasoner (`EpistemicSufficiencyEvaluator`):**
   - Implement evidence quality assessment: distinguish confirmed findings from preliminary tests, unverified rumors, partial fragments, and proprietary non-disclosures.
   - Prevent premature `SUPPORTED` resolution; enforce `INSUFFICIENT_EVIDENCE` abstention.
   - Synthesize `state.final_epistemic_status` directly from resolved question topology.

4. **Phase 5: Evaluator Independence:**
   - Audit claim support metric and document that lexical overlap is an empirical heuristic rather than formal NLI entailment.
   - Keep Benchmark V2 frozen; generate a fresh, independent holdout for post-remediation validation.
