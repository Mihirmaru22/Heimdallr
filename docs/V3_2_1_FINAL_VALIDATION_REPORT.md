# Heimdallr V3.2.1 Final Validation

**System**: Heimdallr Autonomous Intelligence Engine  
**Release Target**: V3.2.1 Release Freeze & Validation Package  
**Candidate Specialist**: `OpenSanctionsSpecialist` (`sanctions_and_beneficial_ownership` via `impl_opensanctions_probe_v1`)  
**Role**: Lead Release-Validation Engineer  
**Status**: RELEASE_FROZEN  
**Date**: 2026-10-08  

---

## 1. Executive Verdict

### **DECISION: VALIDATED**

> [!IMPORTANT]
> **Validation Qualification**: Validated against the defined frozen V3.2.1 capability, routing, security, cross-specialist, and regression benchmarks. Frozen benchmark validation does not establish universal security against unseen future attacks or production-scale live-web generalization.

All 12 release validation gates are green, supported by verified task-level counterfactual causal proof across four independent evaluation suites:

```
========================================================================================
HEIMDALLR V3.2.1 FINAL RELEASE SCORECARD SUMMARY
========================================================================================
1.  Specialist Causal Gain:             YES (+77.5% pass rate gain, 31 attributable fixes)
2.  Candidate-Disabled Regression:       YES (Pass rate drops 100.0% -> 22.5%)
3.  Positive Routing Validated:          YES (100.0% recall, 35/35 tasks, 0 missed)
4.  Negative Routing Validated:          YES (100.0% precision, 35/35 tasks, 0 false alarms)
5.  Security Benchmark Passes:           YES (32/32 probes defused, 0 violations)
6.  Zero Leakage / Integrity Audit:      YES (AST & runtime isolation clean, guard active)
7.  Zero System Regressions:             YES (Eval V2: 129/129, Inv V1: 25/25, Tests: 387/387)
8.  Cross-Specialist Chaining:           YES (16/16 tasks, 5 decoys rejected)
9.  Deterministic Stability:             YES (0.0 variance across 3 frozen runs)
10. Evidence Provenance Integrity:       YES (100% cited, 0 hallucinations)
11. Epistemic Correctness Preserved:     YES (UNKNOWN/NOT_FOUND strictly preserved)
12. Architecture & License Verified:     YES (COEXIST topology, Apache-2.0 clean-room)
========================================================================================
FINAL VERDICT: VALIDATED | ARCHITECTURE: COEXIST | STATUS: FROZEN
========================================================================================
```

---

## 2. Why V3.2 Was Rejected

Although the initial 42-task specialist recruitment competition (`SPECIALIST_COMPETITION_V1`) demonstrated promising capability (37/42 standalone vs 10/42 incumbent), transitioning the package to system-level validation revealed three critical defects:

1. **Saturated Eval V2 Benchmark**:
   - Pre-V3.2 baseline: 129/129 (100.0%)
   - Post-V3.2 integrated: 129/129 (100.0%)
   - Candidate-disabled ablation: 129/129 (100.0%)
   - *Failure*: Eval V2 evaluated only Verticals 1–3 and contained no sanctions tasks. The unchanged 100% score provided zero causal proof of improvement.
2. **Negative-Only Capability Routing**:
   - `CAPABILITY_MATCH_V2` evaluated 140 tasks, but 0 were positive sanctions tasks.
   - *Failure*: Reporting "100% routing recall" on a dataset containing only true negatives was mathematically meaningless; positive invocation remained completely untested.
3. **Concealed Security Audit Failures**:
   - Historical `proofs/v3_2_security_audit.json` documented 2 probe failures (`prompt_injection` and `shell_payload`) with an explicit verdict of `SECURITY_FAILED`.
   - *Failure*: The executive summary reported 0 violations, papering over an active security defect where un-sanitized instructions entered internal candidate observations.

---

## 3. V3.2.1 Repairs

To resolve these defects without synthetic shortcuts or relaxed thresholds, V3.2.1 introduced:

1. **New Evaluation Suites**:
   - [`SANCTIONS_SPECIALIST_V1`](file:///data/shared/project/PlayGround/Argus/src/argus/evals/sanctions_specialist_v1/tasks.py): 40 frozen holdout tasks covering all 30 sanctions, PEP, and beneficial ownership categories.
   - [`CAPABILITY_ROUTING_SANCTIONS_V1`](file:///data/shared/project/PlayGround/Argus/src/argus/evals/capability_routing_sanctions_v1/tasks.py): 70 tasks (balanced 35 positive and 35 negative).
   - [`V3_2_1_SECURITY_V1`](file:///data/shared/project/PlayGround/Argus/src/argus/evals/security_v1/probes.py): 32 adversarial probes covering 31 exploit vectors.
   - [`CROSS_SPECIALIST_V1`](file:///data/shared/project/PlayGround/Argus/src/argus/evals/cross_specialist_v1/tasks.py): 16 multi-hop chaining and decoy rejection tasks.
2. **Hardened Security Boundary**:
   - Upgraded [`SecurityGateValidator`](file:///data/shared/project/PlayGround/Argus/src/argus/competition/security_gate.py) with recursive text sanitization defusing prompt overrides, shell substitutions, sensitive Linux filesystem paths, SSRF endpoints, and SQL injection patterns.
   - Enforced strict containment: `observation.is_authoritative = False` and `observation.status = ObservationStatus.UNVERIFIED`.
3. **Capability Matching Refinement**:
   - Updated [`src/argus/capability_registry/defaults.py`](file:///data/shared/project/PlayGround/Argus/src/argus/capability_registry/defaults.py) with explicit operations and evidence types.
   - Refined [`CapabilityMatcher._cap_satisfies_evidence`](file:///data/shared/project/PlayGround/Argus/src/argus/capability_registry/matcher.py) to exclude generic legal stopwords (`schedule`, `disclosure`, `notice`, `annex`, `registry`) and prevent false routing collisions.

---

## 4. Causal OpenSanctions Validation

Performance on [`SANCTIONS_SPECIALIST_V1`](file:///data/shared/project/PlayGround/Argus/src/argus/evals/sanctions_specialist_v1/runner.py) across all 4 configurations:

| Configuration | Tasks Passed | Pass Rate | Entity F1 | Evidence Correctness | Temporal Accuracy (All 40) | Temporal Subset Acc (8 Temporal) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Argus Baseline (`A`)** | 9 / 40 | 22.5% | 0.225 | 38.0% | 22.5% | 0.0% |
| **OpenSanctions Standalone (`B`)** | 28 / 40 | 70.0% | 0.832 | 85.0% | 70.0% | 100.0% |
| **Heimdallr Integrated (`C`)** | **40 / 40** | **100.0%** | **1.000** | **100.0%** | **100.0%** | **100.0%** |
| **Candidate Disabled (`D`)** | 9 / 40 | 22.5% | 0.225 | 38.0% | 22.5% | 0.0% |
| **System Delta (`C - A`)** | **+31** | **+77.5%** | **+0.775** | **+62.0%** | **+77.5%** | **+100.0%** |
| **Marginal Delta (`C - D`)** | **+31** | **+77.5%** | **+0.775** | **+62.0%** | **+77.5%** | **+100.0%** |

### Causal Attribution Breakdown
Every single task was audited against the triple counterfactual rule:
$$\mathbf{BASELINE\_FAIL} \longrightarrow \mathbf{INTEGRATED\_PASS} \longrightarrow \mathbf{DISABLED\_FAIL}$$

- **Candidate-Attributable Fixes**: **31 / 40 (77.5%)**
  - **Candidate Standalone Wins (21 tasks)**: Tasks where OpenSanctions standalone succeeded (`sanc_v1_01, 02, 03, 06, 07, 08, 09, 10, 11, 13, 20, 25, 26, 27, 31, 32, 33, 34, 36, 37, 38`).
  - **Coexistence Synergy Wins (10 tasks)**: Tasks where **both** Argus baseline and OpenSanctions standalone failed in isolation, but full integrated Heimdallr succeeded (`sanc_v1_04, 05, 15, 16, 17, 18, 19, 28, 29, 35`).
- **Unchanged Negative/Web Tasks**: **9 / 40 (22.5%)** (`sanc_v1_12, 14, 21, 22, 23, 24, 30, 39, 40`). Correctly passed in both baseline and ablated configurations; zero false credit attributed.

### Reconciliation of Inconsistencies
1. **Temporal Accuracy Metric**:
   - In the initial draft, an asymmetric formula zeroed non-temporal passing tasks in standalone ($8/40 = 20.0\%$).
   - Measured symmetrically across all 40 tasks: OpenSanctions standalone achieved **70.0%** (28/40), integrated achieved **100.0%** (40/40), and baseline achieved **22.5%** (9/40).
   - Measured specifically on the 8 temporal tasks (`sanc_v1_03, 08, 13, 20, 27, 33, 37, 38`): OpenSanctions standalone achieved **100.0%** (8/8), Argus baseline scored **0.0%** (0/8), and candidate-disabled scored **0.0%** (0/8). Both numbers are now clearly defined and reconciled.
2. **Coexistence Synergy Count**:
   - The initial report cited 10 synergy tasks but an `if/elif` shadowing bug in the runner recorded 0 synergy wins in JSON, while the markdown draft had typographical errors on tasks 33 and 39.
   - Traced directly from task-level results, exactly **10 tasks** satisfy `Integrated = PASS`, `Argus = FAIL`, `OpenSanctions = FAIL` (`sanc_v1_04, 05, 15, 16, 17, 18, 19, 28, 29, 35`). The bug was repaired and both artifacts now report **10**.

---

## 5. Routing Validation

Results from [`CAPABILITY_ROUTING_SANCTIONS_V1`](file:///data/shared/project/PlayGround/Argus/src/argus/evals/capability_routing_sanctions_v1/runner.py) across 70 balanced tasks:

| Routing Metric | Measured Result | Benchmark Target | Verdict |
| :--- | :---: | :---: | :---: |
| **Sanctions-Positive Tasks** | **35** | 35 | Evaluated |
| **Sanctions-Negative Tasks** | **35** | 35 | Evaluated |
| **True Positives ($TP$)** | **35** | 35 | Exact match |
| **True Negatives ($TN$)** | **35** | 35 | Exact match |
| **False Positives ($FP$)** | **0** | 0 | Zero false triggers |
| **False Negatives ($FN$)** | **0** | 0 | Zero missed queries |
| **Invocation Precision** | **100.0%** (1.000) | $\ge 90.0\%$ | PASS |
| **Invocation Recall** | **100.0%** (1.000) | $\ge 90.0\%$ | PASS |
| **Invocation F1** | **100.0%** (1.000) | $\ge 90.0\%$ | PASS |
| **False Positive Rate** | **0.0%** | $\le 5.0\%$ | PASS |
| **False Negative Rate** | **0.0%** | $\le 5.0\%$ | PASS |

Zero task-level cheating, zero hidden prompt hints, and zero routing collisions across corporate, identity, infrastructure, or web research domains.

---

## 6. Security Validation

Results from [`V3_2_1_SECURITY_V1`](file:///data/shared/project/PlayGround/Argus/src/argus/evals/security_v1/runner.py):

- **Total Adversarial Probes**: **32**
- **Probes Defused / Sanitized**: **32 (100.0%)**
- **Security Violations Detected**: **0**
- **Authoritative State Poisoning**: **0.0%**
- **Tool Execution Prevention Rate**: **100.0%**
- **Historical Failure Modes Remediated**: **2 / 2** (`prompt_injection` defused to `[DEFUSED_INSTRUCTION_OVERRIDE]`, `shell_payload` defused to `[DEFUSED_SHELL_COMMAND]`).

> [!NOTE]
> **Calibrated Security Finding**: V3.2.1 passed the defined frozen security benchmark, including remediation of the two historical V3.2 failure modes. Frozen benchmark success does not establish universal security against unseen future attack patterns.

---

## 7. Cross-Specialist Validation

Results from [`CROSS_SPECIALIST_V1`](file:///data/shared/project/PlayGround/Argus/src/argus/evals/cross_specialist_v1/runner.py):

- **Total Benchmark Tasks**: **16**
- **Multi-Specialist Chaining Tasks**: **11 / 11 Passed (100.0%)**
- **Decoy / Non-Invocation Tasks**: **5 / 5 Correctly Rejected (100.0%)**
- **Chaining Pass Rate**: **100.0%**
- **Ordering Accuracy**: **100.0%** (No inverted dependencies)
- **Authority Leakage Events**: **0**

Specialists chain harmoniously (`corporate -> sanctions -> identity`, `sanctions -> corporate -> infrastructure`) without state collisions or cyclic dependencies.

---

## 8. Regression

Verification of legacy regression suites under integrated V3.2.1:

| Suite | Tasks / Tests | Result | Status | Interpretation |
| :--- | :---: | :---: | :---: | :--- |
| **Eval V2 Frozen Suite** | 129 / 129 | 129 Passed (100.0%) | PASS | No regression detected |
| **Investigation V1 Suite** | 25 / 25 | 25 Passed (100.0%) | PASS | No regression detected |
| **Capability Match V2** | 140 / 140 | 140 Passed (100.0%) | PASS | No regression detected |
| **Repository Test Suite** | 387 / 387 | 387 Passed (100.0%) | PASS | Complete codebase green |

> [!IMPORTANT]
> **Sensitivity Qualification**: Eval V2 is a low-sensitivity benchmark for OpenSanctions because the benchmark was not designed around sanctions-specific capability gaps. Therefore, 100% Eval V2 after V3.2.1 does NOT mean OpenSanctions improved Eval V2. It means: **NO REGRESSION DETECTED**.

---

## 9. Artifact Integrity

Every metric in this report and the JSON deliverables is derived from one unified source of truth generated synchronously by [`scripts/run_v3_2_1_validation.py`](file:///data/shared/project/PlayGround/Argus/scripts/run_v3_2_1_validation.py):

| Metric Category | Authoritative Source Artifact | Calculation Methodology | Authoritative Result |
| :--- | :--- | :--- | :---: |
| **Sanctions 4-Way Evals** | [`proofs/v3_2_1_attribution.json`](file:///data/shared/project/PlayGround/Argus/proofs/v3_2_1_attribution.json) | Sum of task comparisons ($N=40$) across configs A, B, C, D | 22.5% / 70.0% / 100.0% / 22.5% |
| **Candidate Attribution** | [`proofs/v3_2_1_attribution.json`](file:///data/shared/project/PlayGround/Argus/proofs/v3_2_1_attribution.json) | Count of `BASELINE_FAIL -> INTEGRATED_PASS -> DISABLED_FAIL` | 31 tasks (77.5%) |
| **Coexistence Synergy** | [`proofs/v3_2_1_attribution.json`](file:///data/shared/project/PlayGround/Argus/proofs/v3_2_1_attribution.json) | Count where `Integrated=PASS`, `Baseline=FAIL`, `Standalone=FAIL` | 10 tasks (25.0%) |
| **Capability Routing** | [`proofs/v3_2_1_routing.json`](file:///data/shared/project/PlayGround/Argus/proofs/v3_2_1_routing.json) | Confusion matrix over 70 tasks (35 pos, 35 neg) | 35 TP, 35 TN, 0 FP, 0 FN (100% F1) |
| **Security Probes** | [`proofs/v3_2_1_security.json`](file:///data/shared/project/PlayGround/Argus/proofs/v3_2_1_security.json) | Defused count and violation count over 32 probes | 32 defused, 0 violations |
| **Cross-Specialist** | [`proofs/v3_2_1_cross_specialist.json`](file:///data/shared/project/PlayGround/Argus/proofs/v3_2_1_cross_specialist.json) | Passed chains ($N=11$) and rejected decoys ($N=5$) | 16/16 passed (100.0%) |
| **Regression Regimes** | [`proofs/v3_2_1_regressions.json`](file:///data/shared/project/PlayGround/Argus/proofs/v3_2_1_regressions.json) | Pre vs post comparison across 3 frozen benchmarks | 0 regressions detected |
| **Master Scorecard** | [`proofs/v3_2_1_final_scorecard.json`](file:///data/shared/project/PlayGround/Argus/proofs/v3_2_1_final_scorecard.json) | Structured release rollup schema | `VALIDATED` (Release: V3.2.1) |

No manually edited headline metrics exist. All Markdown reports and JSON scorecard files are strictly synchronized. Missing files trigger explicit build failures.

---

## 10. Known Limitations

In compliance with release engineering honesty, the following operational boundary conditions are explicitly declared:

### VALIDATED:
- Frozen sanctions-specific capability benchmark (40 tasks)
- Frozen positive/negative routing benchmark (70 tasks)
- Frozen security benchmark (32 probes)
- Frozen cross-specialist chaining and decoy benchmark (16 tasks)
- Frozen regression suites (Eval V2, Investigation V1, Capability Match V2, 387 unit tests)

### NOT ESTABLISHED:
- **Live-Web Generalization**: The validation harness tests frozen corpus snapshots; performance against uncurated live web HTML with dynamic obfuscation is unverified.
- **Production-Scale Reliability**: Long-running asynchronous execution at high concurrent investigation volume has not been evaluated.
- **Stochastic Model Variance**: Deterministic benchmark assertions with zero measured variance do not reflect model drift in unpinned production LLM endpoints.
- **Unseen Adversarial Attack Coverage**: Defense against 32 known vectors does not guarantee immunity against novel zero-day prompt injection techniques.
- **Live Source Drift**: Sanctions lists and beneficial ownership registries update continuously; pipeline performance is conditional on regular ETL synchronization.

Do not present frozen 100% benchmark scores as production operational accuracy.

---

## 11. Final Architecture Decision

Based on conclusive causal and synergy evidence:

- **OpenSanctionsSpecialist**: **RECRUIT**
- **Integration Policy**: **COEXIST**
- **Argus**: **RETAIN AS GENERALIST & VERIFIER**
- **OpenSanctions**: **RETAIN AS DOMAIN SPECIALIST**

### Architectural Rationale
Argus Generalist provides statutory company registry lookups, infrastructure graph traversal, and epistemic verification. OpenSanctions Specialist provides deep international sanctions indexing, PEP coverage, and offshore leak mapping. The 10 coexistence synergy wins prove that neither system can replace the other; peak intelligence accuracy requires both operating in unison.

---

## 12. Vertical 5 Gate

### **STATUS: V3.2.1 COMPLETE AND FROZEN**

The V3.2.1 remediation and validation milestone is officially complete. All inconsistencies are resolved, the scorecard is generated from raw task evidence, and the package is sealed.

**Vertical 5 may now be considered for future engineering.**

> [!CAUTION]
> Vertical 5 recruitment and implementation are strictly out of scope for this milestone and are NOT initiated in this release freeze.
