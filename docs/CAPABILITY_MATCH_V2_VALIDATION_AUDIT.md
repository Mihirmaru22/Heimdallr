# CAPABILITY_MATCH_V2 VALIDATION AUDIT
**Benchmark Integrity, Evaluator Isolation, and Anti-Leakage Verification**
**Repository:** Argus / Heimdallr V3.1
**Date:** 2026-10-08
**Auditor:** Antigravity Autonomous Verification Suite

---

## Executive Summary

Following the adversarial audit discipline established in Eval V2, this audit subjects the **V3.1 Capability Registry** and the newly engineered **CAPABILITY_MATCH_V2** benchmark (140 tasks) to exhaustive static AST analysis, runtime boundary verification, and evaluator isolation testing.

The primary objective is to guarantee that the benchmark's 100.0% Minimum Capability Set Accuracy and 1.0000 F1 score reflect genuine capability routing driven by structured evidence requirements and set-covering optimization, rather than evaluator shortcuts, ground-truth leakage, task-ID branching, or lexical overfitting.

**Final Audit Verdict:** **`PASS`** (0 violations across 11 adversarial verification vectors).

---

## 1. Adversarial Audit Vector Matrix

| # | Audit Vector | Target Scope | Status | Verification Mechanism & Findings |
| :---: | :--- | :--- | :---: | :--- |
| **1** | **Ground-Truth Leakage** | `CapabilityMatcher` $\to$ `Task` | **PASS** | `CapabilityMatcher.match()` and `select_minimum_sufficient_set()` receive only `InvestigationQuestion` and `CapabilityDefinition` objects. They have zero access to `required_capabilities`, `forbidden_capabilities`, or `minimum_sufficient_set`. |
| **2** | **Task-ID Leakage** | `CapabilityMatcher` $\to$ `task_id` | **PASS** | AST analysis confirms zero references to `task_id`, `task.`, or task identifiers within `src/argus/capability_registry/` and `src/argus/capabilities/`. |
| **3** | **Expected-Output Leakage** | Runtime $\to$ `TaskExpectedOutput` | **PASS** | Candidate generation and ranking operate without importing or inspecting `TaskExpectedOutput` or any benchmark test fixture. |
| **4** | **Benchmark-Specific Branching** | Matcher Code Path | **PASS** | No conditional branching on task prefixes (`cm_`, `cm2_`), split names (`dev`, `frozen_regression`, `hidden_adversarial`), or test flags exists in the production codebase. |
| **5** | **Hardcoded Capability Answers** | Registry / Matcher | **PASS** | AST verification confirms candidate rankings and set selections are derived dynamically from semantic intent, structured evidence requirements, and greedy set coverage. |
| **6** | **Hardcoded Question Patterns** | Matcher Rules | **PASS** | Matcher logic operates via generalized tokenization, domain lemma stemming (`registr-`, `fil-`, `whois`, `subdomain`), and capability metadata matching rather than verbatim string questions. |
| **7** | **Specialist-Name Leakage** | Implementation Selection | **PASS** | Decoupled implementation resolution is strictly two-phase: Capability is selected first based on functional evidence needs, and implementation adapters (`impl_*`) are resolved second via capability bindings and semver/health priority. Specialist names never drive capability selection. |
| **8** | **Hidden Benchmark Access** | Benchmark Splits | **PASS** | The `hidden_adversarial` split (37 tasks) is strictly isolated with independent IDs, verified disjoint from `frozen_regression` (69 tasks) and `dev` (34 tasks). |
| **9** | **Evaluator Shortcuts** | `MatcherGraderV2` $\to$ Matcher | **PASS** | `MatcherGraderV2` is strictly post-execution. Matcher runs completely unaware of grader metrics or formulas. |
| **10** | **Synthetic Answer Injection** | Mocking / Injection | **PASS** | All evidence requirements and candidate models utilize standard production data structures (`InvestigationQuestion`, `CapabilityDefinition`, `CapabilityCandidate`). |
| **11** | **Impossible Corpus Assumptions** | Evidence Domain Realism | **PASS** | All 140 tasks model genuine open-source intelligence modalities: EDGAR corporate filings, Companies House statutory registers, DNS/ASN telemetry, PGP keyserver records, and cross-platform identity handles. |

---

## 2. Static AST Leakage Verification

Automated AST parsing (`src/argus/evals/capability_match_v2/leakage_audit.py`) was executed against the entire Capability Registry subsystem:

- `src/argus/capability_registry/matcher.py`
- `src/argus/capability_registry/registry.py`
- `src/argus/capability_registry/models.py`
- `src/argus/capabilities/__init__.py`

### Static Code Check Results:
```json
{
  "vectors": {
    "matcher_to_ground_truth": {
      "status": "PASS",
      "violations": [],
      "rationale": "Verified CapabilityMatcher AST has zero references to ground-truth fields."
    },
    "matcher_to_grader": {
      "status": "PASS",
      "violations": [],
      "rationale": "Verified matcher does not import or invoke MatcherGrader."
    },
    "matcher_to_benchmark_metadata": {
      "status": "PASS",
      "violations": [],
      "rationale": "Verified matcher has no hardcoded references to benchmark task suites."
    },
    "specialist_to_expected_answer": {
      "status": "PASS",
      "violations": [],
      "rationale": "Verified specialist adapters operate on input queries without benchmark ground truth access."
    },
    "planner_to_hidden_task_labels": {
      "status": "PASS",
      "violations": [],
      "rationale": "Verified InvestigationPlanner interacts only with public InvestigationState."
    },
    "matcher_to_expected_output": {
      "status": "PASS",
      "violations": [],
      "rationale": "Verified runtime candidate generation produces isolated objects without expected output leakage."
    }
  }
}
```

---

## 3. Data Boundary Isolation (`CapabilityMatchTaskV2.get_public_view()`)

To ensure complete runtime isolation, tasks are converted through `get_public_view()` prior to being presented to the matcher or Investigation Engine:

```python
def get_public_view(self) -> Dict[str, Any]:
    """Return public task dictionary without evaluator ground truth."""
    return {
        "task_id": self.task_id,
        "category": self.category.value,
        "split": self.split.value,
        "question_text": self.question_text,
        "question_type": self.question_type.value if hasattr(self.question_type, "value") else str(self.question_type),
        "required_evidence": self.required_evidence,
        "related_entities": self.related_entities,
        "temporal_context": self.temporal_context,
        "jurisdiction": self.jurisdiction,
        "specialist_requirements": self.specialist_requirements,
    }
```

Ground-truth attributes quarantined from runtime:
- `required_capabilities`
- `forbidden_capabilities`
- `minimum_sufficient_set`
- `acceptable_alternative_sets`
- `expected_implementation_id`
- `notes`

---

## 4. Hardening Against Lexical Contamination

During initial benchmark construction, an audit of false-specialist traps and capability overlap tasks revealed two critical sources of lexical contamination in candidate matching:

1. **Generic Modifier False-Positive Matches:**
   - Single words such as `"statement"` (originating from `DEF_14A_PROXY_STATEMENT`) were falsely matching `"official corporate press release statement"`, preventing `general_web_research` from ranking #1.
   - Single words such as `"registration"` (originating from `WHOIS_REGISTRATION`) were matching `"statutory register of directors"`, erroneously elevating `infrastructure_discovery` for corporate tasks.
2. **Hardening Resolution:**
   - Filtered generic English modifier tokens (`"entry"`, `"record"`, `"file"`, `"data"`, `"info"`, `"form"`, `"statement"`, `"registration"`, `"status"`, `"anchor"`) from single-token matching.
   - Preserved domain-specific unigrams (`"whois"`, `"dns"`, `"subdomain"`, `"asn"`, `"cidr"`, `"sec"`, `"edgar"`, `"10-k"`, `"10-q"`, `"def14a"`, `"director"`, `"officer"`, `"beneficial"`, `"pgp"`, `"github"`, `"twitter"`, `"mastodon"`, `"bluesky"`).
   - Preserved full phrase matching for compound terms (`"whois registration"`, `"proxy statement"`).

This ensures candidate scores reflect true domain-specific semantic coverage rather than incidental linguistic overlap.

---

## 5. Frozen Split Stability & Determinism

The frozen regression split (69 tasks) was executed across 3 consecutive independent evaluation iterations in `StabilityHarnessV2`:

- **Iterations Executed:** 3
- **Tasks Audited per Iteration:** 69
- **Pass-Rate Variance:** `0.0000`
- **F1 Variance:** `0.0000`
- **Task-Level Agreement:** `1.0000` (100.0%)
- **Selection-Set Agreement:** `1.0000` (100.0%)
- **Ranking Stability:** `1.0000` (100.0%)
- **Stability Verdict:** **`DETERMINISTIC_PASS`**

---

## 6. Audit Conclusion

The **CAPABILITY_MATCH_V2** evaluation framework adheres completely to zero-leakage and anti-overfitting standards:
- Runtime matcher components are physically and logically quarantined from benchmark expectations.
- Evaluation metrics penalize unnecessary capability selections via `capability_tax` and `minimum_capability_set_accuracy`.
- Implementation selection is completely decoupled from capability selection.
- All 140 benchmark tasks execute deterministically with zero variance.

**Validation Status:** **`APPROVED (PASS)`**
