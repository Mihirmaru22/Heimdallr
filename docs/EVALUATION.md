# Argus Evaluation Harness (Priority 4)

## Overview

The **Argus Evaluation Harness** is an independent, reproducible measurement system designed to evaluate whether Argus produces **correct, complete, evidence-grounded, efficient, and safe research**.

Unlike unit or integration tests (which prove code-level functional contracts), the evaluation harness treats the complete agent system—execution, state, tool routing, search, Laya System 1 ranking, crawl management, document intelligence, extraction, verification, and synthesis—as the unit of evaluation.

---

## 1. Core Architecture

The harness is structurally decoupled from production code, interacting via immutable audit events and external ground truth:

```text
Benchmark Suite (v1.0)
       ↓
Evaluation Tasks (50 tasks across 9 categories)
       ↓
Argus Runner (Frozen Corpus / Live Web)
       ↓
Argus Controller & Production Stack (Laya + Crawlee + TwoTierFetcher + Worker + Verifier)
       ↓
Trajectory Capture (Immutable Events) + Final Repository State
       ↓
Independent Deterministic Graders (Entity, Field, Claim, Evidence, Epistemic, Security)
       ↓
Metrics & 16-Class Failure Taxonomy
       ↓
Evaluation Report (JSON + Markdown Scorecard + Regression Diff)
```

---

## 2. Benchmark Categories & Automotive V1 Dataset

The benchmark contains **50 research tasks** situated in the US automotive intelligence domain (`src/argus/evals/fixtures/tasks_v1.json`):

1. **Entity Discovery** (8 tasks): OEM discovery, supply chain, tier-1 suppliers, EV startups.
2. **Structured Extraction** (8 tasks): Plant locations, products, square footage, capabilities.
3. **Plant / Facility Discovery** (8 tasks): Megasites, assembly plants, battery parks.
4. **Leadership Research** (6 tasks): CEOs, site managers, plant directors, technical leads.
5. **Multi-hop Research** (6 tasks): Cross-document chains linking JVs to plants, suppliers, and investments.
6. **Temporal Research** (5 tasks): Historical facility transitions (e.g. NUMMI → Tesla, Lordstown → Foxconn).
7. **Contradiction Handling** (5 tasks): Conflicting CapEx, job numbers, and production statistics.
8. **Missing Information / Uncertainty** (2 tasks): Non-public unannounced personnel and facilities requiring calibrated `UNKNOWN` / `NOT_FOUND`.
9. **Adversarial / Prompt Injection** (2 tasks): Untrusted web pages containing prompt injection directives and cloud metadata SSRF traps.

> **Core Subset**: 11 representative tasks are tagged with `is_core=True` for rapid CI sanity checks.

---

## 3. Headline Metrics & Composite Scoring

The harness measures five separate pillars:

### Headline Metrics
- **Entity Resolution Accuracy**: Ratio of correct entity identifications without false merges or splits.
- **Field Accuracy & Recall**: Exact and variation-tolerant matching against acceptable values.
- **Evidence Coverage**: Important factual claims with valid citations / total claims.
- **Evidence Correctness**: Verbatim passage alignment against acquired source documents.
- **Unsupported Claim Rate**: Claims lacking valid verified evidence passages (Headline failure signal).
- **Hallucinated Quote Rate**: Citations containing fabricated or mangled quotes (Headline penalty).
- **Epistemic Accuracy**: Faithful status assignment (`SUPPORTED`, `CORROBORATED`, `INFERRED`, `UNVERIFIED`, `CONTRADICTED`, `UNKNOWN`, `NOT_FOUND`).
- **Status Escalation Errors**: Penalizes ungrounded or contradictory claims promoted to `SUPPORTED`.
- **Security Policy Violations**: Prompt injection compliance, SSRF traversal, and boundary breaches.

### Composite Metric Weights
- Research Quality: 30%
- Evidence Quality: 25%
- Safety & Policy: 20%
- Completeness: 15%
- Efficiency: 10%

---

## 4. 16-Class Root-Cause Failure Taxonomy

Failed tasks receive granular root-cause classifications:
1. `SEARCH_FAILURE`: Queries returned zero or irrelevant results.
2. `DISCOVERY_FAILURE`: Failed to uncover required candidate entities.
3. `ACQUISITION_FAILURE`: Network timeouts, blocks, or crawl errors.
4. `DOCUMENT_EXTRACTION_FAILURE`: Document extractor failed to structure text/tables.
5. `CONTEXT_SELECTION_FAILURE`: Relevant content omitted during context bounding.
6. `ENTITY_RESOLUTION_FAILURE`: Misattributed entities, false merges, or false splits.
7. `CLAIM_EXTRACTION_FAILURE`: Worker failed to extract mandatory claims.
8. `EVIDENCE_ALIGNMENT_FAILURE`: Citations point to passages that do not ground the claim.
9. `VERIFICATION_FAILURE`: Verifier rejected valid evidence or failed to corroborate.
10. `CONTRADICTION_FAILURE`: Failed to detect or resolve conflicting source claims.
11. `TEMPORAL_FAILURE`: Outdated information preferred or sequence confused.
12. `COMPLETENESS_FAILURE`: Incomplete discovery universe coverage.
13. `STOPPING_FAILURE`: Premature termination or wasteful continuation.
14. `SYNTHESIS_FAILURE`: Final dossier failed to synthesize verified claims.
15. `SECURITY_FAILURE`: Followed prompt injection or attempted unauthorized network call.
16. `INFRASTRUCTURE_FAILURE`: Out of memory or unhandled exceptions.

---

## 5. CLI Usage Guide

### Running Benchmark
```bash
# Run the 11-task core subset in frozen deterministic mode
python -m argus.evals run --subset core --output data/evals/baseline_v1_core.json --scorecard data/evals/baseline_v1_core_scorecard.md

# Run all 50 tasks
python -m argus.evals run --subset all --output data/evals/baseline_v1.json --scorecard data/evals/baseline_v1_scorecard.md
```

### Comparing Two Runs (Regression Detection)
```bash
python -m argus.evals compare data/evals/baseline_v1.json data/evals/candidate_run.json --report data/evals/regression_report.md
```

### Multi-Run Stability Assessment
```bash
python -m argus.evals stability --runs 3 --subset core
```

---

## 6. Stable V1 Baseline Reference

The initial Argus V1 baseline run on the Core Benchmark produced:
- **Composite Score**: `80.5 / 100`
- **Task Pass Rate**: `45.5%`
- **Unsupported Claim Rate**: `7.5%`
- **Hallucinated Quote Rate**: `0.0%` (0 fabrications)
- **Status Escalation Errors**: `0`
- **Security Policy Violations**: `0`
- **Avg Runtime / Task**: `52.4 sec`

This baseline serves as the immutable reference point for all future Argus development.
