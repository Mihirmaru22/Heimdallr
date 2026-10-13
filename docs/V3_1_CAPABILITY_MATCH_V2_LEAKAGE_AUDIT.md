# V3.1 — CAPABILITY_MATCH_V2 LEAKAGE AUDIT
**Adversarial Leakage Verification & Boundary Knockout Results**
**Repository:** Argus / Heimdallr V3.1
**Date:** 2026-10-08
**Auditor:** Antigravity Autonomous Verification Suite

---

## Executive Summary

This audit establishes mathematical and programmatic proof that the 100% Minimum-Set Accuracy achieved by Heimdallr V3.1 in `CAPABILITY_MATCH_V2` is free from evaluator ground-truth leakage, task-ID branching, and hidden metadata dependencies.

Every potential leakage channel between the evaluation harness and the runtime Capability Registry was subjected to static AST parsing, runtime guard interception, and adversarial mutation testing.

**Overall Leakage Status:** **`PASS`** (0 violations across 10 formal audit vectors).

---

## 1. Formal Leakage Verification Vector Matrix

| # | Leakage Channel / Vector | Verification Mechanism | Status | Evidence & Audit Findings |
| :---: | :--- | :--- | :---: | :--- |
| **1** | `TaskExpectedOutput` $\to$ Runtime | AST Parsing & Symbol Resolution | **PASS** | `TaskExpectedOutput` is never imported, referenced, or inspected in `src/argus/capability_registry/` or `src/argus/investigation/`. |
| **2** | `required_capabilities` $\to$ Runtime | Pydantic Schema Isolation & Guard | **PASS** | `InvestigationQuestion` schema does not possess this attribute. Attempting to assign it raises `ValueError`. Runtime guard confirms 0 instances in question payloads. |
| **3** | `forbidden_capabilities` $\to$ Runtime | Runtime Interception & Mutation Test | **PASS** | Mutating `forbidden_capabilities` to forbid valid capabilities produces 0 change in runtime matcher routing (Test 3 passes). |
| **4** | `minimum_sufficient_set` $\to$ Runtime | Runtime Interception & Mutation Test | **PASS** | Mutating `minimum_sufficient_set` in task definitions produces 0 change in runtime matcher decisions (Test 4 passes). |
| **5** | `acceptable_alternative_sets` $\to$ Runtime | AST & Attribute Inspection | **PASS** | Field is isolated strictly within `CapabilityMatchTaskV2` and evaluated post-execution by `MatcherGraderV2`. |
| **6** | `grader` $\to$ Runtime | Call Graph & Dependency Check | **PASS** | `MatcherGraderV2` is invoked strictly after matcher execution has completed. Matcher possesses 0 references to grader classes. |
| **7** | Task ID $\to$ Routing Behavior | Codebase Lexical Search & AST | **PASS** | Matcher logic contains zero conditional branching on `task_id`, `task_`, or task identifier substrings. |
| **8** | Benchmark Category $\to$ Routing Behavior | Input Signature Audit | **PASS** | Task category (`OBVIOUS_SINGLE`, `FALSE_SPECIALIST_TRAP`, etc.) is quarantined in `task.category` and never provided to `CapabilityMatcher`. |
| **9** | Hidden Labels $\to$ Routing Behavior | Split Isolation Verification | **PASS** | Hidden adversarial tasks (37 tasks) execute with identical public signatures as Dev/Frozen splits without any metadata flags. |
| **10** | `specialist_requirements` Provenance | Provenance Tracing & Knockout Run | **PASS** | Verified that `specialist_requirements` was empty (`[]`) across all 140 tasks in the benchmark. In Mode B (Blind), setting it explicitly to `[]` yielded identical 100.0% results with zero divergence. |

---

## 2. Capability Label Leakage Guard Implementation

The runtime boundary is guarded by `CapabilityLabelLeakageGuard` (`src/argus/evals/capability_match_v2/capability_label_leakage_guard.py`):

```python
FORBIDDEN_EVALUATOR_ATTRIBUTES = {
    "required_capabilities",
    "forbidden_capabilities",
    "minimum_sufficient_set",
    "acceptable_alternative_sets",
    "expected_implementation_id",
    "expected_entities",
    "expected_relationships",
    "grader",
    "grader_labels",
    "benchmark_answers",
    "hidden_task_labels",
    "simulate_health_states",
}
```

The guard operates in two modes:
1. **Static AST Scanning:** Automatically parses all runtime modules in `src/argus/capability_registry/` and `src/argus/investigation/` to verify no imports or attribute accesses touch benchmark fixtures or grader modules.
2. **Runtime Payload Interception:** Deeply scans any dictionary or object passed to `CapabilityMatcher` before execution, raising `LeakageDetectedException` if any forbidden key is populated.

---

## 3. Section 18 Regression Test Suite Verification

All six mandated regression tests in `src/argus/evals/capability_match_v2/capability_label_leakage_tests.py` execute and pass cleanly:

```text
======================================= test session starts =======================================
collected 6 items

capability_label_leakage_tests.py::test_1_ground_truth_cannot_reach_matcher PASSED         [ 16%]
capability_label_leakage_tests.py::test_2_changing_expected_labels_does_not_change_routing PASSED [ 33%]
capability_label_leakage_tests.py::test_3_changing_forbidden_capabilities_does_not_change_routing PASSED [ 50%]
capability_label_leakage_tests.py::test_4_changing_minimum_sufficient_set_does_not_change_routing PASSED [ 66%]
capability_label_leakage_tests.py::test_5_incorrect_capability_hints_do_not_override_evidence PASSED [ 83%]
capability_label_leakage_tests.py::test_6_production_engine_does_not_inject_evaluator_fields PASSED [100%]

======================================== 6 passed in 0.77s ========================================
```

---

## 4. Production Investigation Engine Verification

To verify that genuine runtime execution does not leak evaluator fields, a live multi-hop investigation session was executed through `InvestigationEngine.start_investigation()`:
- **Investigation ID:** `inv_8ff11fc62754`
- **Questions Generated:** 5 foundational sub-questions
- **Evaluator Leakage Detected:** **`False`** across all 5 generated questions
- **Matcher Selection:**
  - `q_0d1ce014` (Legal standing) $\to$ `corporate_registry_intelligence` (Score: 0.975)
  - `q_ec06af0d` (Infrastructure domains) $\to$ `infrastructure_discovery` (Score: 1.000)

---

## 5. Audit Verdict

**LEAKAGE AUDIT STATUS:** **`PASS`**

There is zero evaluator label leakage into the Capability Registry runtime. The benchmark scores are genuine reflections of autonomous evidentiary matching.
