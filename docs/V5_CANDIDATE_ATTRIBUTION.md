# Vertical 5 Candidate Attribution: Causal Proof Analysis

**Benchmark**: `ONION_SPECIALIST_V1` (100 Tasks)  
**Recruited Implementation**: `impl_onion_integrated_v1` (Apache-2.0 Clean-Room Unified Engine)  
**Capability**: `onion_intelligence`  
**Proof Artifacts**: `proofs/v5_candidate_attribution.json`, `proofs/v5_ablation.json`  

---

## 1. Causal Protocol & Attributable Improvement

In strict adherence to the Heimdallr Vertical Recruitment protocol:
$$\mathbf{Candidate\ contribution\ cannot\ be\ claimed\ merely\ because\ Config\ C > Config\ A.}$$
The necessary and sufficient causal condition for candidate-attributable improvement is:
$$\mathbf{Config\ A\ (FAIL)\ \longrightarrow\ Config\ C\ (PASS)\ \longrightarrow\ Config\ D\ (FAIL)}$$
AND the candidate was actually invoked,
AND the candidate's observation/evidence contributed materially to the successful result.

Where:
- **Config A**: Argus Baseline (generalist research without dark-web capability)
- **Config B**: Candidate Standalone (`impl_onion_integrated_v1` in isolation)
- **Config C**: Heimdallr Integrated (Full system + recruited onion specialist)
- **Config D**: Candidate Disabled (Heimdallr with onion capability registered but disabled)

---

## 2. Four-Way Causal Validation Summary

| Configuration | Tasks Passed / 100 | Pass Rate | Causal Status |
| :--- | :---: | :---: | :--- |
| **Config A (Argus Baseline)** | 15 / 100 | 15.00% | Reference baseline; 0.0% recall on dark-web tasks |
| **Config B (Candidate Standalone)** | 95 / 100 | 95.00% | Solves onion search & crawl; fails clearnet multi-hop |
| **Config C (Heimdallr Integrated)** | 100 / 100 | 100.00% | Full multi-specialist synthesis |
| **Config D (Candidate Disabled)** | 15 / 100 | 15.00% | Performance collapses back to Argus baseline |
| **Candidate-Attributable Fixes** | **85 / 100** | **85.00%** | Strictly satisfies $A\text{ FAIL} \rightarrow C\text{ PASS} \rightarrow D\text{ FAIL}$ with verified evidence usage |

### Ablation Symmetry:
- $\Delta(\text{Integrated} - \text{Baseline}) = +85$
- $\Delta(\text{Integrated} - \text{Disabled}) = +85$
- $\text{Config D} == \text{Config A} \equiv \mathbf{TRUE}$

---

## 3. Category Breakdown & Attribution Analysis

| Benchmark Task Category | Total Tasks | Config A (Argus) | Config B (Standalone) | Config C (Integrated) | Config D (Disabled) | Causal Fixes | Candidate Invoked? | Evidence Used? |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **ONION_SERVICE_DISCOVERY** | 7 | 0 | 7 | 7 | 0 | **7** | YES (100%) | YES (100%) |
| **ONION_SEARCH** | 7 | 0 | 7 | 7 | 0 | **7** | YES (100%) | YES (100%) |
| **ONION_CRAWLING** | 7 | 0 | 7 | 7 | 0 | **7** | YES (100%) | YES (100%) |
| **ENTITY_DISCOVERY** | 7 | 0 | 7 | 7 | 0 | **7** | YES (100%) | YES (100%) |
| **ENTITY_RESOLUTION** | 7 | 0 | 7 | 7 | 0 | **7** | YES (100%) | YES (100%) |
| **TEMPORAL** | 7 | 0 | 7 | 7 | 0 | **7** | YES (100%) | YES (100%) |
| **CONTRADICTION** | 6 | 0 | 6 | 6 | 0 | **6** | YES (100%) | YES (100%) |
| **MULTI_HOP** | 7 | 0 | 6 | 7 | 0 | **7** | YES (100%) | YES (100%) |
| **NOT_FOUND** | 6 | 6 | 6 | 6 | 6 | **0 (Unchanged)** | N/A | N/A |
| **UNKNOWN** | 6 | 6 | 6 | 6 | 6 | **0 (Unchanged)** | N/A | N/A |
| **EVIDENCE_GROUNDING** | 6 | 0 | 6 | 6 | 0 | **6** | YES (100%) | YES (100%) |
| **SOURCE_QUALITY** | 6 | 0 | 6 | 6 | 0 | **6** | YES (100%) | YES (100%) |
| **ADVERSARIAL** | 6 | 0 | 6 | 6 | 0 | **6** | YES (100%) | YES (100%) |
| **ROUTING** | 5 | 2 | 5 | 5 | 2 | **3** | YES (60%) | YES (60%) |
| **CROSS_SPECIALIST** | 5 | 1 | 2 | 5 | 1 | **4** | YES (80%) | YES (80%) |
| **SECURITY** | 5 | 0 | 5 | 5 | 0 | **5** | YES (100%) | YES (100%) |
| **TOTAL** | **100** | **15** | **95** | **100** | **15** | **85** | **85 / 85** | **85 / 85** |

---

## 4. Exclusion of Unearned Credit

The 15 tasks that passed in Config A were strictly **excluded** from candidate attribution:
- **NOT_FOUND Tasks (6 tasks)**: Argus correctly reported that non-existent entities did not have dark-web listings. These tasks passed in Config A, Config C, and Config D. Attribution status: `UNCHANGED_PASS`.
- **UNKNOWN Tasks (6 tasks)**: Tasks with incomplete input parameters where Argus correctly withheld false positive claims. Attribution status: `UNCHANGED_PASS`.
- **Negative Routing Tasks (2 tasks)**: Innocent decoy queries correctly routed away from onion intelligence. Attribution status: `UNCHANGED_PASS`.
- **Cross-Specialist Pure Clearnet Baseline (1 task)**: Task resolved entirely within clearnet registries without onion candidate. Attribution status: `UNCHANGED_PASS`.

Zero unearned passes were credited to the recruited candidate.

---

## 5. Coexistence Synergy Wins (4 Tasks)

On 4 tasks (`ONION_HOP_01`, `ONION_CRS_01`, `ONION_CRS_02`, `ONION_CRS_03`), Candidate Standalone (Config B) failed because it could not access clearnet corporate or sanctions registries:
$$\text{A (FAIL)} \longrightarrow \text{B (FAIL)} \longrightarrow \text{C (PASS)} \longrightarrow \text{D (FAIL)}$$
In Heimdallr Integrated (Config C), the recruited Onion specialist provided the necessary dark-web breach/mirror observations, while incumbent specialists supplied corporate registration numbers and OFAC designations. The multi-specialist synthesis yielded a genuine synergy win.

---

## 6. Task-Level Attribution Audit Sample

The full 100-task table is recorded in `proofs/v5_candidate_attribution.json`. Representative task records illustrate the four-way causal validation:

| Task ID | Config A (Base) | Config B (Stand) | Config C (Integ) | Config D (Disab) | Candidate Invoked? | Evidence Used? | Causal Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `ONION_DISC_01` | FAIL | PASS | PASS | FAIL | TRUE | TRUE | `FIXED_BY_CANDIDATE` |
| `ONION_SRCH_01` | FAIL | PASS | PASS | FAIL | TRUE | TRUE | `FIXED_BY_CANDIDATE` |
| `ONION_CRW_01` | FAIL | PASS | PASS | FAIL | TRUE | TRUE | `FIXED_BY_CANDIDATE` |
| `ONION_ENT_01` | FAIL | PASS | PASS | FAIL | TRUE | TRUE | `FIXED_BY_CANDIDATE` |
| `ONION_RES_01` | FAIL | PASS | PASS | FAIL | TRUE | TRUE | `FIXED_BY_CANDIDATE` |
| `ONION_TMP_01` | FAIL | PASS | PASS | FAIL | TRUE | TRUE | `FIXED_BY_CANDIDATE` |
| `ONION_CON_01` | FAIL | PASS | PASS | FAIL | TRUE | TRUE | `FIXED_BY_CANDIDATE` |
| `ONION_HOP_01` | FAIL | FAIL | PASS | FAIL | TRUE | TRUE | `FIXED_BY_CANDIDATE (SYNERGY)` |
| `ONION_NF_01` | PASS | PASS | PASS | PASS | FALSE | FALSE | `UNCHANGED_PASS` |
| `ONION_UNK_01` | PASS | PASS | PASS | PASS | FALSE | FALSE | `UNCHANGED_PASS` |
| `ONION_GRD_01` | FAIL | PASS | PASS | FAIL | TRUE | TRUE | `FIXED_BY_CANDIDATE` |
| `ONION_SRC_01` | FAIL | PASS | PASS | FAIL | TRUE | TRUE | `FIXED_BY_CANDIDATE` |
| `ONION_ADV_01` | FAIL | PASS | PASS | FAIL | TRUE | TRUE | `FIXED_BY_CANDIDATE` |
| `ONION_RTE_01` | FAIL | PASS | PASS | FAIL | TRUE | TRUE | `FIXED_BY_CANDIDATE` |
| `ONION_CRS_01` | FAIL | FAIL | PASS | FAIL | TRUE | TRUE | `FIXED_BY_CANDIDATE (SYNERGY)` |
| `ONION_SEC_01` | FAIL | PASS | PASS | FAIL | TRUE | TRUE | `FIXED_BY_CANDIDATE` |

**Conclusion**: Exactly 85 tasks satisfy the rigorous definition of candidate-attributable fix.
