# Vertical 5 Routing Report: CAPABILITY_ROUTING_ONION_V1

**Benchmark Suite**: `CAPABILITY_ROUTING_ONION_V1` (100 Frozen Routing Tasks: 50 Positive, 50 Negative)  
**Evaluator**: `CapabilityMatcher` & `ImplementationSelector`  
**Proof Artifact**: `proofs/v5_routing.json`  

---

## 1. Executive Summary & Routing Metrics Overview

To ensure transparent reporting and prevent misleading aggregate claims, capability routing for Vertical 5 is explicitly separated across four distinct operational dimensions:

| Routing Metric Dimension | Evaluated Value | Benchmark Threshold | Status |
| :--- | :---: | :---: | :---: |
| **A. Binary Onion Invocation Classification** | **100.00%** | $\ge 95.0\%$ | **PASS** |
| **B. Minimum Capability-Set Accuracy** | **85.00%** | $\ge 80.0\%$ | **PASS** |
| **C. Unnecessary Auxiliary Invocations** | **15** | $\le 20$ | **PASS** |
| **D. Implementation Selection Accuracy** | **100.00%** | $100.0\%$ | **PASS** |

The final benchmark result **MUST NOT** be summarized merely as "Routing = 100%" without qualification. The distinction between binary invocation classification and minimum capability-set accuracy reflects two different operational requirements.

---

## 2. Dimension A: Binary Onion Invocation Classification (100.0%)

This dimension measures whether Heimdallr correctly classifies whether a task requires dark-web intelligence or not:
- **Total Routing Tasks**: 100
- **Actual Positives (Dark-Web Inquiries)**: 50
- **Actual Negatives (Non-Dark-Web Inquiries)**: 50

### Confusion Matrix:
```
                      PREDICTED POSITIVE       PREDICTED NEGATIVE
ACTUAL POSITIVE (50)        TP = 50                  FN = 0
ACTUAL NEGATIVE (50)        FP = 0                   TN = 50
```

- **True Positives (TP)**: 50 / 50 (100.0%)
- **True Negatives (TN)**: 50 / 50 (100.0%)
- **False Positives (FP)**: 0 (0.0%)
- **False Negatives (FN)**: 0 (0.0%)
- **Binary Classification Precision**: **100.00%**
- **Binary Classification Recall**: **100.00%**
- **Binary Classification F1 Score**: **100.00%**
- **Routing Regret**: **0.0000** (Zero unnecessary onion specialist invocations on negative queries)

---

## 3. Dimension B: Minimum Capability-Set Accuracy (85.0%)

Minimum capability-set accuracy measures whether the capability matcher invoked **strictly the minimal set of necessary capabilities** for a query without recruiting superfluous secondary specialists.

- **Tasks Matching Strict Minimum Set**: 85 / 100 (85.00%)
- **Tasks Matching Expanded Capability Set**: 15 / 100 (15.00%)
- **Minimum Capability-Set Accuracy**: **85.00%**

### Explanation of the Difference:
In 85 tasks, the matcher matched exclusively the minimal capability set (`onion_intelligence` alone for pure dark-web tasks, or specific clearnet specialists for non-onion tasks). In 15 positive dark-web tasks, the matcher correctly recruited `onion_intelligence`, but also redundantly matched an auxiliary general specialist (`general_web_research` or `corporate_registry_intelligence`). 

While this did not degrade intelligence correctness (all 15 tasks executed successfully), it represents non-minimal capability selection. This 85% metric is prominently reported rather than obscured behind the binary 100% score.

---

## 4. Dimension C: Unnecessary Specialist Invocations (15 Invocations)

- **Total Unnecessary Invocations**: 15
- **Distribution**:
  - 10 instances of `general_web_research` matched alongside `onion_intelligence` on pure dark-web queries.
  - 5 instances of `corporate_registry_intelligence` matched on standalone ransomware leak searches.
- **Impact on Latency & Cost**: Incremental overhead of ~$0.001 per invocation; zero impact on factual accuracy.
- **Action Item for Future Tuning**: Refine capability boundary keywords in `defaults.py` to prevent auxiliary overlap on purely dark-web tasks.

---

## 5. Dimension D: Implementation Selection Accuracy (100.0%)

When `onion_intelligence` was invoked, `ImplementationSelector` dynamically evaluated active implementation candidates:
1. `impl_onion_integrated_v1` (Unified Clean-Room, Apache-2.0, F1=0.980, Cost=$0.002)
2. `impl_ahmia_search_v1` (Ahmia Search Adapter, BSD-3-Clause, F1=0.820, Cost=$0.001)
3. `impl_torbot_crawler_v1` (TorBot Clean-Room Adapter, Apache-2.0, F1=0.787, Cost=$0.0015)

In **50 / 50 (100.0%)** positive onion tasks, the selector chose `impl_onion_integrated_v1` based on health checks, latency profiles, and comprehensive feature coverage.

---

## 6. The Anti-Keyword Decoy Test (10 / 10 Decoys Rejected)

To prove that routing is driven by semantic capability requirements rather than naive keyword matching, 10 dedicated adversarial decoy tasks were embedded in the negative set. Each query contains dark-web keywords in an innocent context:

| Decoy Task Query | Innocently Present Keyword | Required Evidence | Selected Capability | Onion Invoked? | Correct? |
| :--- | :--- | :--- | :--- | :---: | :---: |
| "Analyze soil nitrogen requirements for Vidalia sweet onion cultivation in Georgia." | `onion` | Agricultural extension bulletin | `general_web_research` | **NO** | **YES** |
| "Explain cellular autophagy regulation mediated by mammalian target of rapamycin (mTOR)." | `mTOR` | Peer-reviewed biology paper | `general_web_research` | **NO** | **YES** |
| "Study cryptographic cell size in Tor onion routing protocol specification (Dingledine 2004)." | `Tor`, `onion` | IEEE conference paper PDF | `general_web_research` | **NO** | **YES** |
| "Summarize New York Times news reporting on international dark web market takedowns." | `dark web` | Archived newspaper articles | `general_web_research` | **NO** | **YES** |
| "Review quarterly revenue and cloud security ARR for Darktrace PLC on London Stock Exchange." | `Darktrace` | LSE regulatory news service | `corporate_registry_intelligence` | **NO** | **YES** |
| "Explain the origin of the term 'onion skinning' in traditional cel animation techniques." | `onion` | Animation textbook chapter | `general_web_research` | **NO** | **YES** |
| "Inspect culinary recipes for French onion soup with caramelized Gruyere croutons." | `onion` | Culinary database recipe | `general_web_research` | **NO** | **YES** |
| "Read astronomical survey data on the Dark Energy Spectroscopic Instrument (DESI)." | `Dark` | Astrophysical Journal article | `general_web_research` | **NO** | **YES** |
| "Look up patent details for Tor-browser hardware acceleration at European Patent Office." | `Tor-browser` | EPO Espacenet patent sheet | `general_web_research` | **NO** | **YES** |
| "Analyze historical trading volumes for Dark Matter token on decentralized Uniswap pools." | `Dark Matter` | DEX liquidity pool logs | `general_web_research` | **NO** | **YES** |

**Decoy Rejection Rate**: **10 / 10 (100.0%)**. Zero false invocations were triggered by superficial keyword collisions.
