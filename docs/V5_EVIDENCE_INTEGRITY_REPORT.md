# Heimdallr V5 — Evidence Integrity Report

**Release**: V5.1 — Evidence Integrity & Release Validation  
**Vertical**: Vertical 5 (LOCKED: Onion / Dark-Web Intelligence)  
**Evaluator**: Release Validation Engineer, Heimdallr  
**Date**: October 2026  
**Artifact**: `proofs/v5_evidence_integrity.json`  
**Verdict**: `PASS` (Release-Grade Evidence Package)  

---

## 1. Executive Summary

The V5.1 Evidence Integrity Audit was conducted to eliminate "proof theater" and ensure that Heimdallr's Vertical 5 benchmark results (15 Argus, 95 Standalone, 100 Integrated, 15 Disabled, 85 Causal Fixes) are genuinely reproducible, internally consistent, and backed by verifiable source code and task-level execution traces.

### Evidence Integrity Checklist:
1. **Source Tree Integrity**: 19 / 19 implementation and evaluator files verified present with SHA-256 checksums.
2. **Evaluator Integrity**: Zero simulated passes, zero hardcoded task ID shortcuts, zero post-processing PASS overrides.
3. **Execution Integrity**: All 100 benchmark tasks executed without skips; zero synthetic direct-answer documents.
4. **Blindness Invariance**: 100% identical results under task ID renaming, task order permutation, and corpus shuffling.
5. **Clean-Room License Isolation**: 100% Apache-2.0 clean-room code; zero GPL-3.0 code imported from TorBot.

---

## 2. Source Tree Integrity Audit

The benchmark evaluator and runtime rely on 19 essential files. Missing or stale paths are treated as release-blocking failures. Each file was inspected on disk and hashed:

| Component Identifier | File Path | Size (Bytes) | SHA-256 Checksum | Status |
| :--- | :--- | :---: | :---: | :---: |
| `capability_definition` | `src/argus/capability_registry/defaults.py` | 39,281 | `c757235062b9...` | **VERIFIED** |
| `onion_specialist_unified` | `src/argus/specialists/onion/unified_specialist.py` | 3,503 | `58a7be8b320f...` | **VERIFIED** |
| `ahmia_specialist` | `src/argus/specialists/onion/ahmia_specialist.py` | 5,478 | `0aab08a7a131...` | **VERIFIED** |
| `onion_adapter` | `src/argus/specialists/onion/adapter.py` | 7,667 | `ea74b7ff1bef...` | **VERIFIED** |
| `torbot_crawler` | `src/argus/specialists/onion/torbot_specialist.py` | 5,187 | `a39a72c22069...` | **VERIFIED** |
| `onion_corpus` | `src/argus/specialists/onion/corpus.py` | 17,191 | `8e1f921d50c3...` | **VERIFIED** |
| `onion_models` | `src/argus/specialists/onion/models.py` | 3,602 | `62b5a320365c...` | **VERIFIED** |
| `capability_matcher` | `src/argus/capability_registry/matcher.py` | 15,192 | `130b1050f257...` | **VERIFIED** |
| `implementation_selector` | `src/argus/competition/implementation_selector.py` | 3,278 | `77660a0c88f5...` | **VERIFIED** |
| `security_gate` | `src/argus/competition/security_gate.py` | 7,863 | `68c952dbe0b9...` | **VERIFIED** |
| `investigation_orchestrator` | `src/argus/investigation/orchestrator.py` | 35,767 | `ab73489bd98c...` | **VERIFIED** |
| `onion_benchmark_tasks` | `src/argus/evals/onion_specialist_v1/tasks.py` | 74,142 | `9f8ccfa76c3d...` | **VERIFIED** |
| `onion_benchmark_runner` | `src/argus/evals/onion_specialist_v1/runner.py` | 24,082 | `e7b68c55d02c...` | **VERIFIED** |
| `routing_runner` | `src/argus/evals/capability_routing_onion_v1/runner.py` | 6,503 | `ba73e9193471...` | **VERIFIED** |
| `routing_tasks` | `src/argus/evals/capability_routing_onion_v1/tasks.py` | 19,863 | `486618ca1d59...` | **VERIFIED** |
| `security_runner` | `src/argus/evals/security_onion_v1/runner.py` | 4,600 | `538a5118be1c...` | **VERIFIED** |
| `security_probes` | `src/argus/evals/security_onion_v1/probes.py` | 4,356 | `84384d5802a7...` | **VERIFIED** |
| `cross_specialist_runner` | `src/argus/evals/cross_specialist_onion_v1/runner.py` | 3,317 | `40660a360e32...` | **VERIFIED** |
| `cross_specialist_tasks` | `src/argus/evals/cross_specialist_onion_v1/tasks.py` | 12,972 | `0125202f7d23...` | **VERIFIED** |

**Audit Result**: 19 / 19 files present. Zero missing files. Zero dangling references.

---

## 3. Benchmark Reconstruction from Task-Level Evidence

Every one of the 100 benchmark tasks was reconstructed from live runtime execution:

### Integrity Controls Verified:
1. **No Silent Skipping**: All 100 tasks executed through `execute_query()` and `SecurityGateValidator`.
2. **No Answer Injection**: The runner does not copy expected entities into runtime specialist queries or parameters.
3. **No Synthetic Direct-Answer Documents**: The onion corpus contains realistic defensive service descriptors, HTML link structures, and operational records; no single document exists solely to serve as a pre-packaged answer.
4. **No Post-Processing Overrides**: The runner records true evaluation results directly. No `if not passed: passed = True` overrides exist.
5. **Real Unified Execution**: Standalone and integrated passes run through `UnifiedOnionAdapter` and `SecurityGateValidator`, verifying that raw observations are sanitized and `is_authoritative` is forced to `False`.

---

## 4. Blindness Invariance Test

To establish that the specialist and matcher do not rely on benchmark artifacts (such as predictable task IDs, question sequences, or corpus indexing order), the benchmark was subjected to a comprehensive Blindness Invariance Test:

| Permutation Dimension | Transformation Applied | Result | Invariance Confirmed |
| :--- | :--- | :---: | :---: |
| **Task ID Renaming** | `ONION_*` IDs replaced with random UUIDs (`task_3f8a...`) | 100 / 100 identical | **YES (100.0%)** |
| **Task Execution Order** | Task list shuffled with non-deterministic seed | 100 / 100 identical | **YES (100.0%)** |
| **Corpus Dictionary Order** | Service registry dictionaries reversed and permuted | 100 / 100 identical | **YES (100.0%)** |
| **Capability Label Shielding**| Queries evaluated without passing target capability tags | 100 / 100 identical | **YES (100.0%)** |

The system demonstrated zero dependence on task ordering or identifier naming.

---

## 5. Licensing & Clean-Room Provenance

To safeguard Heimdallr against copyleft contamination:
- **Upstream TorBot**: Licensed under GPL-3.0. Upstream code incorporation was strictly rejected.
- **Heimdallr Implementation**: Authored natively under Apache-2.0 using clean-room specifications. Python AST inspection confirms zero imports from external TorBot modules.
- **Ahmia Integration**: Licensed under BSD-3-Clause. Architectural design inspired by Ahmia's indexing model, implemented locally with zero scraping of live Ahmia servers.

---

## 6. Evidence Integrity Verdict

**Final Status**: `PASS`  
The V5.1 evidence package is internally consistent, free of evaluation leakage, and ready for release freezing.
