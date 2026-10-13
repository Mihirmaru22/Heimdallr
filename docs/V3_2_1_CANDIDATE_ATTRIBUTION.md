# Heimdallr V3.2.1 Candidate Attribution Report

**Causal Validation Artifact**  
**Benchmark**: `SANCTIONS_SPECIALIST_V1` (40 Tasks)  
**Evaluator**: Lead Validation Engineer  
**Status**: CAUSAL_GAIN_VALIDATED  
**Date**: 2026-10-08  

---

## 1. Causal Attribution Methodology

A common pitfall in AI agent recruitment is declaring an improvement "candidate-attributable" simply because the newly recruited candidate was invoked during the investigation. 

In Heimdallr V3.2.1, we enforce the **strict four-way counterfactual causal test**:

1. **Pre-Candidate Baseline (`ARGUS_BASELINE`)**: Must fail the candidate-dependent task due to lack of domain-specific intelligence.
2. **Integrated System (`HEIMDALLR_INTEGRATED`)**: Must resolve the task with high entity precision, correct relationship topology, and verified evidence.
3. **Candidate Ablation (`CANDIDATE_DISABLED`)**: Must deterministically regress back to failure on the exact same task when the recruited candidate is removed or disabled.
4. **Specialist Standalone (`OPENSANCTIONS_STANDALONE`)**: Evaluated in isolation to distinguish specialist domain knowledge from system-level orchestration synergy.

### Causal Test Criterion
$$\text{Causal Pattern} = \mathbf{BASELINE\_FAIL} \longrightarrow \mathbf{INTEGRATED\_PASS} \longrightarrow \mathbf{DISABLED\_FAIL}$$

If a task passes under `ARGUS_BASELINE`, it is classified as `UNCHANGED` regardless of whether the specialist was invoked. Only tasks exhibiting the true triple causal pattern are credited as `FIXED_BY_CANDIDATE`.

---

## 2. Comprehensive Task-Level Attribution Table

The table below reports the complete results across all 40 tasks in `SANCTIONS_SPECIALIST_V1`:

| Task ID | Category | Baseline (`A`) | Standalone (`B`) | Integrated (`C`) | Disabled (`D`) | Invoked? | Candidate Contribution | Verified? | Causal Attribution |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- | :---: | :--- |
| `sanc_v1_01` | Sanctions screening | FAIL | PASS | **PASS** | FAIL | YES | OFAC SDN screening | YES | **FIXED_BY_CANDIDATE** |
| `sanc_v1_02` | Sanctioned-entity ID | FAIL | PASS | **PASS** | FAIL | YES | EU restrictive measures ID | YES | **FIXED_BY_CANDIDATE** |
| `sanc_v1_03` | Alias resolution | FAIL | PASS | **PASS** | FAIL | YES | Phonetic alias matching | YES | **FIXED_BY_CANDIDATE** |
| `sanc_v1_04` | Beneficial ownership | FAIL | FAIL | **PASS** | FAIL | YES | BVI trust controller | YES | **FIXED_BY_CANDIDATE** (Synergy) |
| `sanc_v1_05` | Ownership traversal | FAIL | FAIL | **PASS** | FAIL | YES | Multi-tier trust unmasking | YES | **FIXED_BY_CANDIDATE** (Synergy) |
| `sanc_v1_06` | PEP identification | FAIL | PASS | **PASS** | FAIL | YES | Government PEP record | YES | **FIXED_BY_CANDIDATE** |
| `sanc_v1_07` | Offshore entities | FAIL | PASS | **PASS** | FAIL | YES | Panama Papers vehicle | YES | **FIXED_BY_CANDIDATE** |
| `sanc_v1_08` | Jurisdiction conflicts | FAIL | PASS | **PASS** | FAIL | YES | US vs EU listing delta | YES | **FIXED_BY_CANDIDATE** |
| `sanc_v1_09` | Historical sanctions | FAIL | PASS | **PASS** | FAIL | YES | Historical OFAC listing date | YES | **FIXED_BY_CANDIDATE** |
| `sanc_v1_10` | Delisting status | FAIL | PASS | **PASS** | FAIL | YES | Historical removal notice | YES | **FIXED_BY_CANDIDATE** |
| `sanc_v1_11` | Temporal reasoning | FAIL | PASS | **PASS** | FAIL | YES | Listing vs transaction date | YES | **FIXED_BY_CANDIDATE** |
| `sanc_v1_12` | Negative: Non-sanctioned | **PASS** | PASS | **PASS** | **PASS** | YES | Clean screening report | YES | UNCHANGED |
| `sanc_v1_13` | Ambiguous names | FAIL | PASS | **PASS** | FAIL | YES | DOB/passport resolution | YES | **FIXED_BY_CANDIDATE** |
| `sanc_v1_14` | Common-name collision | **PASS** | PASS | **PASS** | **PASS** | YES | True negative disambiguation | YES | UNCHANGED |
| `sanc_v1_15` | Corporate $\to$ Sanctions | FAIL | FAIL | **PASS** | FAIL | YES | Corporate officer OFSI hit | YES | **FIXED_BY_CANDIDATE** (Synergy) |
| `sanc_v1_16` | Sanctions $\to$ Corporate | FAIL | FAIL | **PASS** | FAIL | YES | SDN entity UK registry check | YES | **FIXED_BY_CANDIDATE** (Synergy) |
| `sanc_v1_17` | Corp $\to$ Sanc $\to$ Ident | FAIL | FAIL | **PASS** | FAIL | YES | 3-hop multi-specialist chain | YES | **FIXED_BY_CANDIDATE** (Synergy) |
| `sanc_v1_18` | Corp $\to$ Sanc $\to$ Infra | FAIL | FAIL | **PASS** | FAIL | YES | Blocked firm telecom infra | YES | **FIXED_BY_CANDIDATE** (Synergy) |
| `sanc_v1_19` | Multi-hop ownership | FAIL | FAIL | **PASS** | FAIL | YES | 4-tier holding chain | YES | **FIXED_BY_CANDIDATE** (Synergy) |
| `sanc_v1_20` | Contradiction | FAIL | PASS | **PASS** | FAIL | YES | Name spelling conflict | YES | **FIXED_BY_CANDIDATE** |
| `sanc_v1_21` | Missing information | **PASS** | PASS | **PASS** | **PASS** | YES | Identified epistemic gap | YES | UNCHANGED |
| `sanc_v1_22` | NOT_FOUND | **PASS** | PASS | **PASS** | **PASS** | YES | Confirmed zero matches | YES | UNCHANGED |
| `sanc_v1_23` | UNKNOWN | **PASS** | PASS | **PASS** | **PASS** | YES | Unindexed offshore shell | YES | UNCHANGED |
| `sanc_v1_24` | Adversarial material (neg) | **PASS** | FAIL | **PASS** | **PASS** | YES | Debunked spoofed clearance | YES | UNCHANGED |
| `sanc_v1_25` | Syndicated evidence | FAIL | PASS | **PASS** | FAIL | YES | Consolidated watchlist hit | YES | **FIXED_BY_CANDIDATE** |
| `sanc_v1_26` | Stale evidence | FAIL | PASS | **PASS** | FAIL | YES | Reconciled revoked license | YES | **FIXED_BY_CANDIDATE** |
| `sanc_v1_27` | Conflicting evidence | FAIL | PASS | **PASS** | FAIL | YES | Resolved UN vs EU status | YES | **FIXED_BY_CANDIDATE** |
| `sanc_v1_28` | Cross-jurisdiction ER | FAIL | FAIL | **PASS** | FAIL | YES | Multi-country entity match | YES | **FIXED_BY_CANDIDATE** (Synergy) |
| `sanc_v1_29` | Beneficial-owner depth | FAIL | FAIL | **PASS** | FAIL | YES | 5-hop beneficial owner depth | YES | **FIXED_BY_CANDIDATE** (Synergy) |
| `sanc_v1_30` | False-positive match (neg) | **PASS** | PASS | **PASS** | **PASS** | YES | Prevented false match | YES | UNCHANGED |
| `sanc_v1_31` | Secondary sanctions | FAIL | PASS | **PASS** | FAIL | YES | Sectoral secondary sanctions | YES | **FIXED_BY_CANDIDATE** |
| `sanc_v1_32` | Maritime evasion | FAIL | PASS | **PASS** | FAIL | YES | Shadow fleet IMO lookup | YES | **FIXED_BY_CANDIDATE** |
| `sanc_v1_33` | Temporal 50% attribution | FAIL | PASS | **PASS** | FAIL | YES | Aggregate 50% blocked share | YES | **FIXED_BY_CANDIDATE** |
| `sanc_v1_34` | Nominee shareholder | FAIL | PASS | **PASS** | FAIL | YES | Nominee trust unmasking | YES | **FIXED_BY_CANDIDATE** |
| `sanc_v1_35` | Ownership chain traversal | FAIL | FAIL | **PASS** | FAIL | YES | Multi-jurisdiction trust chain | YES | **FIXED_BY_CANDIDATE** (Synergy) |
| `sanc_v1_36` | PEP identification | FAIL | PASS | **PASS** | FAIL | YES | Regional PEP declaration | YES | **FIXED_BY_CANDIDATE** |
| `sanc_v1_37` | Alias resolution | FAIL | PASS | **PASS** | FAIL | YES | Transliterated Cyrillic alias | YES | **FIXED_BY_CANDIDATE** |
| `sanc_v1_38` | Temporal reasoning | FAIL | PASS | **PASS** | FAIL | YES | Sanctions enforcement timeline | YES | **FIXED_BY_CANDIDATE** |
| `sanc_v1_39` | Clean fund negative | **PASS** | PASS | **PASS** | **PASS** | YES | Verified unlisted EU fund | YES | UNCHANGED |
| `sanc_v1_40` | Adversarial decree spoof (neg)| **PASS** | FAIL | **PASS** | **PASS** | YES | Debunked forged decree | YES | UNCHANGED |

---

## 3. Causal Attribution Summary

```
Total Benchmark Tasks:                     40 (100.0%)
Fixed By Recruited Candidate:              31 ( 77.5%)
  - Candidate Standalone Wins:             21 ( 52.5%)
  - Coexistence Synergy Wins:              10 ( 25.0%)
Unchanged (Correct in Baseline & Ablated):  9 ( 22.5%)
Causal Attribution Ratio:                 31 / 31 (100.0% of observed gains)
False Positives Introduced:                 0 (  0.0%)
Epistemic Regressions Introduced:           0 (  0.0%)
```

### Key Analytical Takeaways

1. **Definitive Causal Delta**:
   - `ARGUS_BASELINE` pass rate: **22.5%** (9/40)
   - `HEIMDALLR_INTEGRATED` pass rate: **100.0%** (40/40)
   - `CANDIDATE_DISABLED` pass rate: **22.5%** (9/40)
   - **Net System Improvement**: **+77.5%** ($+31$ tasks)
   - **Marginal Candidate Delta**: **+77.5%** ($+31$ tasks)
2. **Coexistence Synergy (10 Tasks)**:
   - On tasks requiring multi-hop corporate verification and beneficial ownership traversal (`sanc_v1_04`, `05`, `15`, `16`, `17`, `18`, `19`, `28`, `29`, `35`), `OPENSANCTIONS_STANDALONE` failed (0/10) because it lacks cross-domain corporate registry parsing and infrastructure tracing.
   - `ARGUS_BASELINE` failed (0/10) because it lacks consolidated global sanctions coverage and offshore leaks indexes.
   - **Only the integrated Heimdallr system passed all 10 synergy tasks**, conclusively validating the **COEXIST** architectural policy.
3. **Argus Verifier Preserves Epistemic Correctness**:
   - On all 31 candidate-fixed tasks, every candidate observation was ingested as `is_authoritative = False` and subjected to Argus claim-level corroboration.
   - Zero hallucinated evidence and zero false-positive merges occurred.
