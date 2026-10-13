# HEIMDALLR EVAL V2 — BASELINE 1.0 (FROZEN)
## Official Frozen Evaluation Baseline for Full Heimdallr Stack

**Frozen Date:** October 2026  
**Status:** FROZEN REFERENCE BASELINE (IMMUTABLE)  
**Evaluator Architecture:** Genuine Execution (Eval V2.1)  
**Corpus Inventory:** 175 Total Registered Documents (Reconciled from intermediate 156 figure)  

---

## 1. Frozen Baseline Overview

This document formally establishes **Heimdallr Eval V2 — Baseline 1.0**.
It freezes the exact performance of the Full Heimdallr Stack (Argus Research Core + Clean-Room Identity Specialist + Native Infrastructure Specialist + Regulatory Corporate Specialist + Argus Verifier Gatekeeper) on the genuine, non-leaking Eval V2 benchmark.

---

## 2. Core Quantitative Scorecard

| Dimension | Frozen Baseline 1.0 Score | Benchmark Scope |
| :--- | :---: | :--- |
| **Total Benchmark Tasks** | **129** | Full multi-category benchmark suite |
| **Full-Stack Pass Rate** | **84.5%** (109 / 129) | All verification & epistemic criteria satisfied |
| **Entity Precision** | **87.2%** | Discovered entities grounded in evidence |
| **Entity Recall** | **92.5%** | Target entity coverage across domains |
| **Entity F1 Score** | **89.8%** | Harmonic mean of precision & recall |
| **Multi-Hop Chain Completion** | **88.9%** | Full iterative relational graph traversal |
| **Temporal Accuracy** | **87.5%** | Correct resolution at historical date $T$ |
| **Epistemic Accuracy** | **91.5%** | Correct claim status assignment |
| **Evidence Correctness** | **96.2%** | Grounded snippets from authoritative docs |
| **Critical Failures** | **0** | Zero prompt injection leaks or false merges |
| **Major Failures** | **20** | Unsolved research tasks (Detailed below) |

---

## 3. Corpus Document Reconciliation (175 vs 156)

During the audit, a discrepancy was noted between 175 registered documents in `CORPUS_V2_REGISTRY` and an earlier mention of 156 documents in `docs/EVAL_V2_CORPUS_QUALITY_REPORT.md`:

- **Audit Finding:** The 156 count represented an intermediate staging checkpoint containing the primary regulatory and technical backing documents.
- **Final Reconciled Inventory:** 19 additional fixtures were added to provide realistic academic controls, negative search noise, and syndicated wire mirrors:
  - 51 Companies House filings
  - 46 SEC EDGAR filings (Forms 10-K, 10-K/A, Exhibit 21)
  - 34 News & financial reporting articles
  - 18 Certificate Transparency logs
  - 11 OSINT & developer profiles
  - 7 DNS zone & nameserver records
  - 5 Academic literature papers
  - 3 Syndicated wire service copies
  - **Total: 175 fully registered, discoverable documents.**
- **Resolution:** All documentation, test harnesses, and validation scripts now uniformly report the exact 175 document census.

---

## 4. Frozen Failure Distribution (The 20 Unsolved Tasks)

The remaining 15.5% failure rate comprises exactly 20 tasks, cleanly distributed across four failure classes:

| Failure Class | Count | Primary Affected Categories | Failure Characteristic |
| :--- | :---: | :--- | :--- |
| **Budget Exhaustion** | **8** | Cat 08 (Deep Multi-Hop), Cat 19 | Iterative search quota reached before resolving terminal nodes (hops $\ge 5$) |
| **Multi-Jurisdiction Ambiguity** | **6** | Cat 10 (Offshore), Cat 16 (Cross-Border) | Disjoint national entities sharing corporate brand names without cross-index |
| **Temporal / Restatement Reasoning**| **4** | Cat 09 (Historical), Cat 24 (Restatements) | Resolving multiple sequential amendments with overlapping effective dates |
| **Adversarial Syndication** | **2** | Cat 22 (Adversarial PR Rings) | Multiple press releases sharing syndicated wire text mistaken for independent corroboration |
| **Total** | **20** | — | — |

This frozen failure distribution forms the empirical basis for Phase 2 failure-driven engineering.
