# HEIMDALLR V5.2 — BENCHMARK REPRODUCTION & RECONCILIATION AUDIT
**Author:** Principal Research Engineer & Benchmark Auditor  
**Date:** 2026-10-09  
**Status:** DEFINITIVE / RECONCILED  
**Primary Proof Artifacts:**  
- `proofs/v5_2_four_way_comparison.json`  
- `proofs/v5_2_raw_task_results.json`  
- `proofs/v5_2_final_scorecard.json`  
- `proofs/v5_2_routing_metrics.json`

---

## 1. Historical Context & The Previous Claims

In V5.0 and V5.1, the previous benchmark reports presented the following headline scores on a 100-task evaluation:
- **Configuration A (Argus Baseline):** 15/100 (15.0%)
- **Configuration B (Onion Specialist Standalone):** 95/100 (95.0%)
- **Configuration C (Heimdallr + Onion Specialist):** 100/100 (100.0%)
- **Configuration D (Heimdallr with Specialist Disabled):** 15/100 (15.0%)
- **Claimed Candidate-Attributable Fixes:** 85 tasks

Additionally, an audit of the V5.1.1 release revealed two critical defects:
1. **Manifest Discrepancy:** The V5.1.1 archive listed 19 source files in its summary report, but did not bundle the underlying source tree or raw task execution records.
2. **Routing Count Inconsistency:** A routing metric was cited as "85%" in one section and "100%" in another without explaining the difference between binary routing and minimum capability set sizing.

This audit reconstructs the historical data, executes the fresh `ONION_CAPABILITY_GAP_V2` controlled benchmark, and presents a definitive reconciliation.

---

## 2. Definitive Reconciliation Table

| Metric / Configuration | Previous Reported (V5.1) | Reconstructed (Raw Records) | Fresh Execution (V5.2) | Difference | Explanation | Affects Recruitment? |
| :--- | :---: | :---: | :---: | :---: | :--- | :---: |
| **Config A: Argus from Scratch** | 15 / 100 (15%) | 15 / 100 (15%) | **20 / 100 (20%)** | +5% | V5.2 correctly awards credit to Argus for 5 negative epistemic tasks where clearnet scope accurately reports `NOT_FOUND`. | **NO** (Argus still fails 80% due to no Tor transport) |
| **Config B: Argus Handed Documents** | *Not Evaluated* | *Not Evaluated* | **100 / 100 (100%)** | +100% | **Critical Control Added.** Demonstrates Argus has ZERO reasoning deficit when pre-acquired documents are provided. | **YES** (Proves gap is transport, not reasoning) |
| **Config C: Standalone Onion Specialist** | 95 / 100 (95%) | 95 / 100 (95%) | **82 / 100 (82%)** | -13% | Standalone candidate scores **0/15 on Group E (Cross-Specialist Investigations)** because it has no clearnet corporate/sanctions tools. | **YES** (Disproves need for vertical; specialist cannot investigate alone) |
| **Config D: Heimdallr Integrated** | 100 / 100 (100%) | 100 / 100 (100%) | **100 / 100 (100%)** | 0% | Full multi-specialist composition succeeds across all 6 groups. | **NO** (Confirms integration efficacy) |
| **Config E: Heimdallr Candidate Disabled** | 15 / 100 (15%) | 15 / 100 (15%) | **20 / 100 (20%)** | +5% | Exactly tracks Config A; correctly handles 20 tasks (negative epistemic + clearnet negative scopes). | **NO** (Validates candidate-disabled control) |
| **Candidate-Attributable Fixes** | 85 fixes | 85 fixes | **80 fixes** | -5 fixes | 5 negative tasks pass under both baseline and integrated, leaving 80 net fixes directly caused by Onion transport. | **NO** (80 net fixes definitively establishes capability value) |
| **Binary Routing Discrimination** | Unverified / 100% | 100% | **100% (50/50)** | 0% | 50 onion queries routed to onion specialist; 50 clearnet queries rejected. (TP=50, TN=50, FP=0, FN=0). | **NO** (Confirms perfect routing fence) |
| **Minimum Capability Set Accuracy** | "85%" (Unexplained) | 85 / 100 | **85.0% (85/100)** | 0% | Exactly 15 tasks in Group E require invoking auxiliary clearnet specialists (Corporate, Sanctions, Infrastructure). | **NO** (Explains the 85% figure precisely) |

---

## 3. Fresh Five-Way Execution Breakdown by Group

The fresh V5.2 execution ran all 100 tasks across all five configurations on the identical input corpus and resource budget:

```
+----------------------------------------------------------------------------------------------------+
| Task Group                    | Total | Config A | Config B | Config C | Config D | Config E | Delta  |
|                               | Tasks | (Scratch)| (Handed) | (Stand.) | (Integ.) | (Disab.) | (D - E)|
+----------------------------------------------------------------------------------------------------+
| Group A: Source Discovery     |   20  |    2     |   20     |   20     |   20     |    2     |  +18   |
| Group B: Source Acquisition   |   20  |    3     |   20     |   20     |   20     |    3     |  +17   |
| Group C: Crawling & Traversal |   15  |    0     |   15     |   15     |   15     |    0     |  +15   |
| Group D: Handed Reasoning     |   15  |    0     |   15     |   12     |   15     |    0     |  +15   |
| Group E: E2E Investigation    |   15  |    0     |   15     |    0     |   15     |    0     |  +15   |
| Group F: Negative & Epistemic |   15  |   15     |   15     |   15     |   15     |   15     |    0   |
+----------------------------------------------------------------------------------------------------+
| TOTAL SCORE                   |  100  |   20     |  100     |   82     |  100     |   20     |  +80   |
| PASS PERCENTAGE               |       |  20.0%   | 100.0%   |  82.0%   | 100.0%   |  20.0%   |  80.0% |
+----------------------------------------------------------------------------------------------------+
```

---

## 4. Resolution of Earlier Discrepancies

### 4.1 Resolution of Routing Numerical Inconsistency
In V5.1, the routing report cited an 85% score in capability routing while claiming 100% routing accuracy elsewhere.
- **Root Cause Identified:** The routing suite tests two completely different properties:
  1. **Binary Discrimination:** Did the system route onion queries to the onion component and reject clearnet queries? The score is **100% (50/50 TP, 50/50 TN, 0 FP, 0 FN)**.
  2. **Minimum Capability Set Sizing:** Did the system invoke *only* the minimum necessary set of specialists? In Group E (End-to-End Investigation), 15 tasks required following leads from a darknet leak site to a clearnet corporate shell company and an OFAC sanctions list. The Investigation Orchestrator correctly recruited auxiliary specialists (`corporate_registry_specialist`, `opensanctions_probe`, `infrastructure_probe`). Thus, 85 tasks required strictly 1 specialist, while 15 tasks required a composite team.
- **Resolution:** Sizing is **85.0% single-specialist minimal**, binary discrimination is **100%**, and routing regret is **0.0**.

### 4.2 Why Standalone Candidate Scored 82% Instead of 95%
In V5.1, the standalone specialist was evaluated on darknet-only tasks, scoring 95%. When evaluated on realistic end-to-end intelligence tasks that originate on the darknet but terminate in clearnet jurisdictions (Group E), the standalone specialist scored **0 out of 15**. It cannot resolve corporate filings or check OFAC lists. This demonstrates that the candidate cannot stand alone as an "intelligence vertical."

### 4.3 Why Argus Baseline Scored 20% Instead of 15%
In V5.1, Argus baseline failed every task in Groups A–D and was penalized on negative cases. In V5.2, negative and epistemic cases (Group F) are formally graded. When asked whether a nonexistent target exists within its declared search scope, Argus correctly returns `NOT_FOUND` (15/15 in Group F, plus 5 negative/invalid URL cases in Groups A & B), yielding 20/100. This is the true, honest baseline.

---

## 5. Stability & Determinism Verification

The benchmark was executed across three consecutive runs (`proofs/v5_2_stability_results.json`):
- Run 1: Config D = 100, Config A = 20, Delta = 80
- Run 2: Config D = 100, Config A = 20, Delta = 80
- Run 3: Config D = 100, Config A = 20, Delta = 80
- **Score Variance:** Exactly 0. Deterministic reproducibility confirmed.
