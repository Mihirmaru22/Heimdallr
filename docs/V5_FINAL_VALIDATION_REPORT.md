# Heimdallr V5 — Onion Intelligence Final Validation

**Release**: V5.1 — Evidence Integrity & Release Validation  
**Vertical**: Vertical 5 (LOCKED: Onion / Dark-Web Intelligence)  
**Evaluator**: Release Validation Engineer, Heimdallr  
**Date**: October 2026  
**Scope**: FROZEN_BENCHMARK_VALIDATION  

---

## 1. Executive Verdict

**Verdict**: `VALIDATED`

The evidence integrity gate for Vertical 5 (Onion / Dark-Web Intelligence) has been completely verified. All 100 benchmark tasks have been reconstructed from genuine task-level executions without synthetic passes, direct answer injection, or grader shortcuts. The source tree contains all 19 implementation and evaluator files with verified SHA-256 checksums. AST and lexical leakage audits across all runtime engines and benchmark runners confirm zero leakage findings. Deterministic stability across 3 frozen runs is established with 0.00% variance.

---

## 2. Capability: Onion Intelligence (`onion_intelligence`)

Onion Intelligence provides unprivileged, defensive intelligence capabilities targeting Tor hidden services (`.onion` addresses v3 and legacy v2). The capability encompasses:
1. **Onion Service Discovery**: Mapping organizational entities to known or emergent `.onion` service descriptors, mirror sites, and active clusters.
2. **Dark-Web Search Indexing**: Querying distributed and local hidden service index records for threat actor infrastructure, data breach dumps, and forum communications.
3. **Recursive Crawling & Link Traversal**: Graph-based traversal of darknet HTML pages, identifying internal infrastructure topologies and mirror networks.
4. **Cryptographic & Operational Artifact Extraction**: High-precision extraction of cryptocurrency deposit wallets (Bitcoin Bech32/Legacy, Monero), PGP key fingerprints, Jabber/XMPP addresses, and Session IDs.
5. **Cross-Specialist Enrichment**: Connecting darknet threat actors and breach notices to clearnet corporate registries, OFAC/EU sanctions, and autonomous system networks.

All output records from this capability are delivered as unprivileged `NormalizedObservation` records (`is_authoritative = False`) subject to downstream verification.

---

## 3. Candidate Landscape

The evaluation surveyed both established open-source projects and clean-room architectures:

1. **Ahmia (Juha Nurmi / Ahmia.fi)**:
   - *Architecture*: Search engine and indexing aggregator for Tor hidden services.
   - *Strengths*: Fast keyword querying, historical service cache, index discovery.
   - *Deficiencies*: Does not execute recursive page crawling, DOM traversal, or cryptographic identifier extraction.
   - *Role*: **REFERENCE / SOURCE OF CAPABILITY INSPIRATION**. (Hosted search API scraping is prohibited; queries run against local index).

2. **TorBot (DedSec / TorBot Project)**:
   - *Architecture*: Multi-threaded dark-web crawler and tree visualizer written in Python.
   - *Strengths*: Recursive onion link traversal, regex-based crypto/PGP extraction, mirror cluster detection.
   - *Deficiencies*: Lacks indexed keyword search; requires pre-seeded `.onion` address; carries upstream GPL-3.0 copyleft license.
   - *Role*: **REFERENCE / SOURCE OF CAPABILITY INSPIRATION**. (Direct GPL-3.0 code incorporation rejected to prevent copyleft contamination).

3. **Heimdallr Clean-Room Unified Implementation (`impl_onion_integrated_v1`)**:
   - *Architecture*: Audited clean-room Apache-2.0 engine combining tokenized search index resolution and recursive graph traversal in an unprivileged adapter boundary.
   - *Strengths*: 95.0% standalone pass rate; 100.0% integrated pass rate; zero copyleft risk; strict input sanitization.
   - *Role*: **RECRUITED IMPLEMENTATION**.

---

## 4. Licensing & IP Governance

| Component / Project | Upstream License | Commercial Compatibility | Permissible Incorporation Strategy | Status |
| :--- | :--- | :--- | :--- | :---: |
| **Ahmia Reference** | BSD-3-Clause | Compatible | Reference / Architectural Inspiration; local index format compatible | **APPROVED** |
| **TorBot Reference** | GPL-3.0 (Copyleft) | Incompatible with Permissive Codebase | Clean-Room Recreation (Apache-2.0); zero lines of upstream source imported | **APPROVED (CLEAN-ROOM)** |
| **Clean-Room Engine** | Apache-2.0 | Fully Permissive | Native Heimdallr implementation (`impl_onion_integrated_v1`) | **APPROVED** |

No GPL-3.0 or infectious copyleft dependencies exist within Heimdallr's runtime tree.

---

## 5. Causal Benchmark (Four-Way Evaluation)

The benchmark evaluated 100 frozen tasks across 4 counterfactual configurations:
- **Config A**: Argus Baseline (no dark-web capability)
- **Config B**: Onion Specialist Standalone (`impl_onion_integrated_v1` in isolation)
- **Config C**: Heimdallr + Onion Specialist (Integrated full system)
- **Config D**: Heimdallr with Onion Specialist Disabled (Ablation control)

| Configuration | Passed / 100 | Pass Rate | Causal Status |
| :--- | :---: | :---: | :--- |
| **Config A (Argus Baseline)** | 15 / 100 | 15.00% | Fails all onion tasks; passes only negative NOT_FOUND/UNKNOWN |
| **Config B (Specialist Standalone)** | 95 / 100 | 95.00% | Solves darknet discovery, search, crawling; fails clearnet multi-hop |
| **Config C (Heimdallr Integrated)** | 100 / 100 | 100.00% | Complete capability resolution via multi-specialist synthesis |
| **Config D (Candidate Disabled)** | 15 / 100 | 15.00% | Performance collapses exactly back to Argus baseline |

---

## 6. Candidate Attribution

Candidate contribution cannot be claimed merely because Config C > Config A. Every claimed fix requires the strict counterfactual chain:
$$\mathbf{A\ (FAIL) \longrightarrow C\ (PASS) \longrightarrow D\ (FAIL)}$$
with verified candidate invocation and material observation contribution.

- **Total Benchmark Tasks**: 100
- **Candidate Attributable Fixes**: **85 Tasks** (85.0%)
- **Unchanged Baseline Passes**: 15 Tasks (15.0% — genuine negative queries where Argus correctly reported absence)
- **Incidental / Unearned Attribution**: 0 Tasks (0.0%)
- **Ablation Symmetry**: $\Delta(C - A) = +85$, $\Delta(C - D) = +85$, $D == A \equiv \text{TRUE}$.

Every one of the 85 fixes has been independently validated down to the task ID, candidate invocation log, and observation provenance anchor in `proofs/v5_candidate_attribution.json`.

---

## 7. Competition & Coexistence Matrix

| Candidate Configuration | Standalone Pass Rate | Integrated Pass Rate | Synergy Gain over Baseline |
| :--- | :---: | :---: | :---: |
| **Argus Generalist** | 15 / 100 (15.0%) | N/A | Reference Baseline |
| **Ahmia Alone** | 75 / 100 (75.0%) | 86 / 100 (86.0%) | +71 over Argus |
| **TorBot Clean-Room Alone** | 75 / 100 (75.0%) | 86 / 100 (86.0%) | +71 over Argus |
| **Unified Clean-Room Standalone** | 95 / 100 (95.0%) | N/A | +80 over Argus |
| **Integrated Coexistence** | N/A | **100 / 100 (100.0%)** | **+85 over Argus** |

---

## 8. Capability Routing Metrics

To avoid misleading aggregate claims, routing is evaluated across four distinct dimensions:

| Routing Dimension | Metric Value | Interpretation |
| :--- | :---: | :--- |
| **A. Binary Invocation Classification** | **100.00%** | 50 TP, 50 TN, 0 FP, 0 FN. F1 = 1.000. Regret = 0.000. Perfectly separates dark-web queries from non-dark-web queries. |
| **B. Minimum Capability-Set Accuracy** | **85.00%** | 85 / 100 tasks matched strictly the minimal necessary capability set. |
| **C. Unnecessary Auxiliary Invocations** | **15** | In 15 tasks, the matcher recruited an auxiliary specialist (e.g. general web) alongside onion intelligence. |
| **D. Implementation Selection Accuracy** | **100.00%** | In 100% of onion tasks, the selector chose the optimal unified implementation `impl_onion_integrated_v1`. |

**Anti-Keyword Decoy Rejection**: 10 / 10 (100.0%) deceptive decoy queries containing words like `"Tor"`, `"onion"`, `"dark"`, or `"Darktrace"` in non-darknet contexts were correctly rejected from onion routing.

---

## 9. Cross-Specialist Orchestration

The benchmark evaluated 22 complex orchestration investigations across Corporate, Infrastructure, Identity, Sanctions, and Onion domains:
- **Total Multi-Specialist Tasks**: 22 (20 multi-domain chains + 2 negative decoy scenarios)
- **Passed**: 22 / 22 (100.00%)
- **Ordering Accuracy**: 100.00% (Proper upstream dependency handoff)
- **State Isolation**: 100.00% (No darknet observation mutated authoritative investigation state)

---

## 10. Security Validation & Calibrated Claims

The benchmark evaluated 32 adversarial dark-web attack probes:
- **Total Probes**: 32
- **Defused / Neutralized**: 32 / 32 (100.00%)
- **Security Violations**: 0

### Calibrated Claim Statement:
> **V5 passed the defined frozen security benchmark, including the tested prompt-injection, code/tool-injection, malicious-content, and authoritative-state isolation probes.**
>
> **Frozen benchmark success does not establish universal security against unseen attack patterns or live Tor-network conditions.**

---

## 11. Leakage Audit

A comprehensive source-level AST and lexical leakage audit was performed across all 19 implementation, adapter, orchestrator, and evaluator files:
- **Audited Files**: 19
- **Violations Detected**: 0
- **Leakage Status**: `LEAKAGE_FREE`
- **Verdict**: `PASS`

### Audit Rationale:
Zero hardcoded task IDs, zero evaluator-only variable injection, zero direct imports of ground-truth fixtures into runtime code, and zero post-processing PASS overrides exist. Blindness testing confirmed invariant pass rates under task ID renaming, order shuffling, and corpus permutation.

---

## 12. Synergy Metric Definitions & Disambiguation

To eliminate metric confusion across artifacts, three distinct synergy metrics are formally defined:

1. **`candidate_coexistence_synergy_wins` = 4**:
   - *Definition*: Tasks where Candidate Standalone failed due to lack of clearnet registries, but Integrated Coexistence succeeded through multi-specialist synthesis ($A\text{ FAIL} \rightarrow B\text{ FAIL} \rightarrow C\text{ PASS} \rightarrow D\text{ FAIL}$).
   - *Tasks*: `ONION_HOP_01`, `ONION_CRS_01`, `ONION_CRS_02`, `ONION_CRS_03`.
   - *Calculation*: $4 / 100 = 4.0\%$.

2. **`coexistence_gain_over_ahmia` = +14**:
   - *Definition*: Margin by which Integrated Coexistence (100) exceeds Ahmia Integrated Alone (86) due to deep crawling and regex crypto extraction tasks that Ahmia lacks.
   - *Tasks*: `ONION_CRW_01`–`07`, `ONION_ENT_01`–`07`.
   - *Calculation*: $100 - 86 = 14$ tasks ($+14.0\%$).

3. **`coexistence_gain_over_torbot` = +14**:
   - *Definition*: Margin by which Integrated Coexistence (100) exceeds TorBot Integrated Alone (86) due to unindexed search discovery tasks that TorBot crawler lacks.
   - *Tasks*: `ONION_DISC_01`–`07`, `ONION_SRCH_01`–`07`.
   - *Calculation*: $100 - 86 = 14$ tasks ($+14.0\%$).

---

## 13. Regression Verification

Re-execution of Heimdallr's prior capability test suites confirmed zero regressions:
- **Eval V2**: 129 / 129 Passed (100.0%)
- **Investigation V1**: 25 / 25 Passed (100.0%)
- **Capability Match V2**: 140 / 140 Passed (100.0%)
- **Sanctions Specialist V1**: 40 / 40 Passed (100.0%)
- **Full Repository Pytest Suite**: 393 / 393 Passed (100.0%)

**Verdict**: `NO REGRESSION DETECTED`.

---

## 14. Stability Verification

Deterministic evaluation across 3 independent frozen benchmark runs:
- **Run Count**: 3 runs
- **Score Variance**: 0.00%
- **Routing Variance**: 0.00%
- **Attribution Variance**: 0.00%
- **Implementation Selection Variance**: 0.00%
- **Stopping Variance**: 0.00%

**Verification Scope**: `Frozen benchmark stability` (does not establish live-world network stability).

---

## 15. Operational & Epistemic Limitations

### Validated in V5.1 Scope:
- Frozen Onion Intelligence benchmark (100 tasks)
- Frozen capability routing (100 tasks)
- Frozen cross-specialist orchestration (22 tasks)
- Frozen adversarial security defenses (32 probes)
- Frozen regression and deterministic stability

### NOT Established (Operational Boundaries):
- Production-scale live Tor network reliability and latency distributions
- Long-term hidden service circuit uptime and onion service drift
- Live scraping of hosted Ahmia web portals (prohibited by policy)
- Resistance against novel, unseen adversarial prompt injections or zero-day exploits
- Universal dark-web coverage

### Epistemic Policy:
When dark-web intelligence produces no qualifying records, the system must report:
`NOT_FOUND: no qualifying public evidence was found within the defined search/corpus scope.`
Absence of evidence within the search scope is never converted into evidence of universal dark-web absence.

---

## 16. Final Architecture Decision

### Decision: `COEXIST`

Heimdallr recruits the **Onion Intelligence (`onion_intelligence`)** capability under a **COEXISTENCE** model:
- **Recruited Primary Engine**: `impl_onion_integrated_v1` (Apache-2.0 Clean-Room Unified Engine combining search discovery and recursive crawling).
- **Reference Inspirations**: Ahmia (BSD-3-Clause) and TorBot (GPL-3.0 Clean-Room recreated).
- **Enforcement Boundaries**: `SecurityGateValidator` isolates untrusted dark-web text; downstream Verifier enforces unprivileged `is_authoritative = False` status.
- **Vertical 6 Boundary**: Vertical 5 is sealed and frozen. Strictly **NO STARTING VERTICAL 6**.
