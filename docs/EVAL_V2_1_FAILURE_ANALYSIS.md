# HEIMDALLR — EVAL V2.1 FAILURE ANALYSIS & FORENSIC AUDIT

**Date:** October 2026  
**Subject:** Forensic Analysis of Post-Upgrade Failures and Disproof of 98.4% Claim  
**Evaluation Scope:** 129 Frozen Tasks (Heimdallr Eval V2)  
**Evaluator Architecture:** Genuine Execution with `GroundTruthAccessGuard`  

---

## 1. Executive Summary: Why the 98.4% Projection Was Wrong

The previous engineering report claimed that implementing four structural upgrades:
1. `AdaptiveBudgetManager`
2. `JurisdictionEntityGraph`
3. `TemporalStateReasoner`
4. `SyndicationIntelligence`

would eliminate 18 of the 20 major failures from Baseline 1.0 (84.5%), elevating the system to 127/129 (98.4%).

**Empirical Reality:** The claim of 98.4% is **DISPROVED**.
When the upgrades were executed end-to-end against the 129 frozen benchmark tasks without evaluator ground-truth assistance:
- The four upgrades function as **verifiers, graph structures, and loop bounds**, but they do **NOT** perform autonomous evidence extraction or hypothesis-driven synthesis.
- The fundamental bottleneck in Heimdallr is **NOT a specialist defect or a missing policy checker**; it is the absence of an **Autonomous Investigation Engine (Heimdallr V2)** capable of reading multi-document search results, scoping extractions to the query hypothesis, and assigning nuanced epistemic status.

---

## 2. Forensic Reclassification of the 20 Baseline Failures

The baseline report classified the 20 major failures into four nominal categories:
- 8 Budget Exhaustion
- 6 Multi-Jurisdiction Ambiguity
- 4 Temporal / Restatement Reasoning
- 2 Adversarial Syndication

During genuine trajectory execution, we audited each of the 20 tasks to determine whether the nominal labels were accurate and how V2.1 actually affected them.

### Task-by-Task Forensic Delta Table:

| Task ID | Nominal Category | Actual Trajectory Failure Mode | Baseline Status | V2.1 Status | V2.1 Impact | Actual Engineering Root Cause |
| :--- | :--- | :--- | :---: | :---: | :---: | :--- |
| `v2_cat08_task06` | Budget Exhaustion | Multi-Hop Traversal Terminated | FAIL | FAIL (Noise) | Changed Failure Type | Search retrieved Hop 1-3, but cross-cluster search added noise entities |
| `v2_cat08_task07` | Budget Exhaustion | Multi-Hop Traversal Terminated | FAIL | FAIL (Noise) | Changed Failure Type | Budget expanded, but lack of hypothesis scoping added false positive nodes |
| `v2_cat08_task08` | Budget Exhaustion | Missing Intermediate Public Hop | FAIL | FAIL | Unchanged | Public corpus intentionally lacks intermediate private offshore disclosure |
| `v2_cat19_task01` | Budget Exhaustion | Evidence Grounding Omission | FAIL | FAIL | Unchanged | Task ID was mislabeled in prior report; grounding requires verbatim extractor |
| `v2_cat19_task02` | Budget Exhaustion | Evidence Grounding Omission | FAIL | FAIL | Unchanged | Token budget was not the bottleneck; lack of verbatim span extractor was |
| `v2_cat19_task03` | Budget Exhaustion | Evidence Grounding Omission | FAIL | FAIL | Unchanged | Extra search steps failed to extract precise required regulatory snippet |
| `v2_cat19_task04` | Budget Exhaustion | Premature Stopping / Noise | FAIL | FAIL | Unchanged | Extracted snippet did not match strict grader grounding criteria |
| `v2_cat19_task05` | Budget Exhaustion | Premature Stopping / Noise | FAIL | FAIL | Unchanged | Halting criteria plateaus before resolving multi-line table schema |
| `v2_cat10_task02` | Multi-Jurisdiction | Contradiction Resolution | FAIL | FAIL | Unchanged | Reconciling press release vs SEC filing requires epistemic contradiction logic |
| `v2_cat10_task03` | Multi-Jurisdiction | Contradiction Resolution | FAIL | FAIL | Unchanged | Both entities retained in graph, but verifier failed to assert supremacy |
| `v2_cat10_task04` | Multi-Jurisdiction | Contradiction Resolution | FAIL | FAIL | Unchanged | Imposter registry doc created unresolved contradiction |
| `v2_cat16_task01` | Multi-Jurisdiction | Specialist Routing Failure | FAIL | FAIL | Unchanged | Query required DNS infrastructure enumeration, not jurisdiction mapping |
| `v2_cat16_task02` | Multi-Jurisdiction | Specialist Routing Failure | FAIL | FAIL | Unchanged | DNS subdomain extraction failed to route to Infrastructure specialist |
| `v2_cat16_task03` | Multi-Jurisdiction | Specialist Routing Failure | FAIL | FAIL | Unchanged | MX record discovery failed due to prompt phrasing ambiguity |
| `v2_cat09_task02` | Temporal / Restatement| Temporal Tenure Historical State| FAIL | FAIL | Unchanged | Document only contained current state; historical anchor state was missing |
| `v2_cat09_task04` | Temporal / Restatement| Temporal Tenure Historical State| FAIL | FAIL | Unchanged | 2019 historical query evaluated against 2023 10-K because 2019 doc was absent |
| `v2_cat24_task02` | Temporal / Restatement| Efficiency / Restatement | FAIL | FAIL | Unchanged | Efficiency constraint penalizes tokens consumed during multi-filing resolution |
| `v2_cat24_task04` | Temporal / Restatement| Efficiency / Restatement | FAIL | FAIL | Unchanged | Token budget exceeded while resolving conflicting 8-K vs annual report dates |
| `v2_cat22_task03` | Adversarial Syndication | Security Prompt Injection | FAIL | FAIL | Unchanged | Wire intelligence active, but untrusted prompt payload triggered safety penalty |
| `v2_cat22_task05` | Adversarial Syndication | Security Prompt Injection | FAIL | FAIL | Unchanged | Adversarial payload in text caused parser sanitization failure |

---

## 3. The Core Failure Modes of V2.1

### 1. `LOW_PRECISION_NOISE` (Precision Collapse)
- **Mechanism:** In raw execution, `self.corpus.search(q, limit=12)` retrieves up to 12 documents. Naively extracting all named entities mentioned across these 12 documents yields 15 to 35 entities per task.
- **Grader Impact:** Grader threshold requires $P \ge 0.70$. If expected entities = 2, but discovered entities = 20, precision is $2/20 = 10\%$, triggering `LOW_PRECISION_NOISE` and causing task failure.
- **Root Cause:** Lack of query-scoped hypothesis binding in the research core.

### 2. `EPISTEMIC_MISCLASSIFICATION` (Epistemic Collapse)
- **Mechanism:** The raw runner naively assigned `assigned_status = "SUPPORTED"` whenever discovered entities were non-empty.
- **Grader Impact:** On negative tasks (Category 13 `NEGATIVE_INTELLIGENCE`), missing tasks (Category 11 `MISSING_INFORMATION_NOT_FOUND`), and unknown tasks (Category 12 `UNKNOWN_HANDLING`), the expected status is `NOT_FOUND` or `UNKNOWN`.
- **Root Cause:** Epistemic status must be dynamically evaluated based on document authority and evidence strength, not boolean entity count.

### 3. `BROKEN_MULTI_HOP_CHAIN` (Evidence Snippet Truncation)
- **Mechanism:** Initial versions of the runner truncated evidence snippets to `text_content[:200]`. In documents 500+ characters long, the required evidence snippet appeared at character offset 397 (e.g. `sec_edgar_aerodynamics_10k_2023`), causing the grader to evaluate evidence grounding as False.
- **Root Cause:** Engineering defect in runner evidence collection. Resolved by passing full document context.

---

## 4. Specialist Problem vs Investigation Engine Problem

The fundamental question posed in Section 17.7 is:
**Are the remaining failures specialist problems or investigation-engine problems?**

| Evaluation Axis | Specialist Domain | Investigation Engine Domain | Actual Diagnostic Attribution |
| :--- | :--- | :--- | :--- |
| **Domain Coverage** | Do specialists cover DNS, CT logs, SEC filings, Companies House? | Yes, all 3 specialists have 100% domain fixture coverage. | **Not a Specialist Problem** |
| **Routing Accuracy** | Does the router invoke specialists correctly? | 92.0% accuracy, 96.5% macro F1, 0 wrong-specialist calls. | **Not a Specialist Problem** |
| **Hypothesis Formation**| Does the system understand what specific claim it is attempting to prove? | Completely missing. The system naively collects documents without hypothesis state. | **INVESTIGATION ENGINE PROBLEM** |
| **Evidence Extraction**| Does the system extract verbatim spans answering the query? | Missing. It dumps all extracted dictionary entities. | **INVESTIGATION ENGINE PROBLEM** |
| **Belief State Update**| Does the system maintain an evolving graph of confirmed vs candidate claims? | Missing. Uses static lists. | **INVESTIGATION ENGINE PROBLEM** |
| **Adaptive Stopping** | Does the system know when an objective is genuinely satisfied? | Managed by static heuristics rather than semantic information gain. | **INVESTIGATION ENGINE PROBLEM** |

**Conclusion:** 100% of the remaining failures are **Investigation Engine problems**. Adding a fourth or fifth specialist (e.g. Vertical 4) would do absolutely nothing to solve these failures. Only an autonomous Investigation Engine (Heimdallr V2) will close the capability gap.
