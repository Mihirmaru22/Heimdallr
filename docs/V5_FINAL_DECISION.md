# Vertical 5 Final Decision: Onion Intelligence Capability Recruitment

**Vertical**: VERTICAL 5 (LOCKED: ONION / DARK-WEB INTELLIGENCE)  
**Recruitment Verdict**: `V5_COEXIST`  
**Primary Implementation**: `impl_onion_integrated_v1` (Apache-2.0 Clean-Room Unified Engine)  
**Date**: October 2026  
**Auditor**: Vertical Recruitment Engineer, Heimdallr  

---

## 1. Final Recruitment Gate Verification (12-Point Checklist)

Every requirement of the Vertical 5 recruitment gate (Section 22) has been rigorously evaluated and verified against counterfactual benchmark evidence:

| # | Recruitment Gate Criterion | Benchmark Evidence / Finding | Status |
| :-: | :--- | :--- | :---: |
| **1** | **Real Capability Gap Demonstrated** | Argus baseline passed only 15/100 tasks (15.0%); 0.0% recall on darknet services. | **VERIFIED** |
| **2** | **Candidate Capability Improvement** | Unified specialist standalone passed 95/100 tasks (95.0%). | **VERIFIED** |
| **3** | **Integrated Performance Improvement** | Full Heimdallr + Onion specialist passed 100/100 tasks (100.0%). | **VERIFIED** |
| **4** | **Disabled Ablation Eliminates Improvement** | Disabling candidate reduces performance from 100% back to exactly 15/100 (15.0%). | **VERIFIED** |
| **5** | **Causally Attributable Demonstration** | Exactly 85 tasks satisfy $A \text{ (FAIL)} \rightarrow C \text{ (PASS)} \rightarrow D \text{ (FAIL)}$. | **VERIFIED** |
| **6** | **Reliable Capability Routing** | 100 tasks (50 pos, 50 neg): TP=50, TN=50, FP=0, FN=0; Precision=100%, Recall=100%, F1=100%. | **VERIFIED** |
| **7** | **Cross-Specialist Composition** | 22/22 cross-specialist investigations passed (100.0%); zero ordering or handoff errors. | **VERIFIED** |
| **8** | **Security Benchmark Passes** | 32/32 adversarial probes neutralized; 0 violations; state isolation enforced. | **VERIFIED** |
| **9** | **Licensing Compatibility** | GPL-3.0 avoided via Clean-Room Apache-2.0 implementation; BSD-3-Clause adapter safe. | **VERIFIED** |
| **10** | **Zero Regressions on Prior Capabilities** | Eval V2 (129/129), Inv V1 (25/25), Match V2 (140/140), Sanctions V1 (40/40), Pytest (387/387). | **VERIFIED** |
| **11** | **Leakage Audit Passes** | 14 runtime files scanned via static AST; 0 forbidden terms or ground-truth leakage. | **VERIFIED** |
| **12** | **Deterministic Stability Verified** | 3 independent runs; 0.00% score variance, 0.00% routing variance. | **VERIFIED** |

---

## 2. Final Architectural Decision

### Policy: `V5_COEXIST`

Heimdallr recruits the **Onion Intelligence (`onion_intelligence`)** capability under a **COEXISTENCE** architecture:
1. **No Single Monopoly**: Ahmia and TorBot do not compete as mutually exclusive options. Ahmia provides indexed search discovery; TorBot provides recursive crawling and cryptographic identifier extraction.
2. **Clean-Room License Protection**: To prevent GPL-3.0 copyleft contamination from TorBot, all crawling, link traversal, and regex extraction capabilities are implemented natively as an audited Apache-2.0 clean-room engine.
3. **Primary Production Implementation**: `impl_onion_integrated_v1` orchestrates search and crawling within a single unprivileged adapter boundary, delivering `NormalizedObservation` records (`is_authoritative = False`) to Heimdallr's Verifier.

---

## 3. Scope & Operational Directives

1. **Defensive Research Only**: Heimdallr is restricted to public-information intelligence and defensive research. No exploits, no credential theft, no unauthorized access, no anti-bot circumvention.
2. **Authoritative Isolation**: Untrusted dark-web text remains unprivileged source data until processed by the Verifier.
3. **Vertical 6 Boundary**: Vertical 5 is complete and sealed. **DO NOT START VERTICAL 6**.
