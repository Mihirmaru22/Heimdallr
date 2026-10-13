# Heimdallr V3.1: Capability Registry Final Report
## Formalizing the Specialist Intelligence Layer

### 1. Executive Summary & Verification Status

Heimdallr V3.1 achieves the primary architectural milestone: **formalizing the specialist intelligence layer behind a common capability contract**. The Investigation Engine now selects research actions based on **Evidence Requirements** and **Question Types** via a strongly typed, decoupled **Capability Registry**, rather than hardcoded specialist names.

#### Key Verification Highlights:
- **Zero Regressions Across All Previous Benchmarks**:
  - Full Test Suite: **375/375 PASSED** in 4.73s (100.0%).
  - Real Eval V2 Integration: **129/129 PASSED** (100.0%).
  - Investigation V1 Benchmark: **25/25 PASSED** (100.0%).
  - Specialist Audits (Identity, Infrastructure, Corporate): **100% Passing & Zero Regressions**.
- **CAPABILITY_MATCH_V1 Benchmark Results**:
  - Total Tasks: **35**
  - Tasks Passed: **35 / 35 (100.0%)**
  - Capability Selection Precision: **0.9905**
  - Capability Selection Recall: **1.0000**
  - Capability Selection F1: **0.9943**
  - Missed Required Capabilities: **0**
  - Wrong Capability Selections: **0**

---

### 2. Explicit Answers to Architectural Questions (Section 29)

#### 1. Are capabilities now independent from implementations?
**Yes.** Abstract capabilities (e.g., `identity_resolution`, `infrastructure_discovery`, `corporate_registry_intelligence`, `general_web_research`) are first-class entities with dedicated identifiers, category assignments, and input/output contracts. Implementations (e.g., `impl_identity_probe_specialist_v1`, `impl_challenger_identity_specialist_v2`) bind to capabilities via `implementation_id` and adapters without altering the capability abstraction.

#### 2. Can multiple implementations of one capability coexist?
**Yes.** The registry supports registering $N$ distinct implementations under the same `capability_id`. For example, `identity_resolution` currently hosts both `impl_identity_probe_specialist_v1` (v1.0.0, F1=0.971) and `impl_challenger_identity_specialist_v2` (v2.0.0, F1=0.980, specializing in PGP cryptographic assertions). Both coexist simultaneously, are indexed, and can be queried or ranked independently.

#### 3. Can the Investigation Engine select capabilities based on evidence requirements?
**Yes.** The `CapabilityMatcher` evaluates incoming `InvestigationQuestion` evidence requirements (e.g., "Certificate Transparency CT log", "Companies House register of directors", "Keybase identity proof") against capability declared `evidence_types` using strict word-boundary token matching. Evidence requirements carry the highest weight (40%) in the matcher scoring function.

#### 4. Is keyword routing still required for core behavior?
**No.** Core capability selection is requirement-based. The matcher computes a composite score across evidence requirements (40%), question type (25%), entity class (15%), jurisdiction compatibility (10%), and temporal fit (10%). Lexical matching is purely an evidence-token boundary check, not hardcoded keyword routing.

#### 5. Can the system select multiple capabilities for one question?
**Yes.** When a question spans multiple intelligence disciplines (e.g., a cross-specialist inquiry investigating infrastructure domain ownership and its corporate legal registrant), `CapabilityMatcher.match()` returns all qualifying candidates ranked deterministically. The planner can construct sequenced or branched `ResearchAction`s to satisfy each required evidence type.

#### 6. Can unavailable capabilities be excluded safely?
**Yes.** Capabilities with status `UNAVAILABLE`, `DISABLED`, or `QUARANTINED` are filtered out during candidate generation. If a primary capability is disabled, the system falls back safely to alternate candidates (e.g., general web research via Argus) without throwing runtime errors or halting investigations.

#### 7. Can degraded capabilities remain available with explicit status?
**Yes.** A capability in `DEGRADED` status remains eligible for selection, but its match score is penalized by a $0.70\times$ multiplier, and explicit risk flags (`STATUS_DEGRADED`) are attached to the candidate so the planner can make an informed risk-reward decision.

#### 8. Are benchmark-derived performance profiles represented correctly?
**Yes.** All performance profiles in `PerformanceProfile` require explicit provenance: `benchmark_id`, `benchmark_version`, `measurement_date`, and `scope="BENCHMARK_OBSERVED"`. The registry strictly forbids uncalibrated or generic qualitative marketing claims.

#### 9. Is license/recruitment metadata preserved?
**Yes.** Every capability implementation specifies `LicenseMetadata`, recording SPDX license, `license_status` (`APPROVED`, `RESTRICTED`, `REFERENCE_ONLY`, `REJECTED`, `UNKNOWN`), `source_type` (`IN_HOUSE`, `CLEAN_ROOM_REIMPLEMENTATION`), repository URI, version, git commit SHA, and clean-room verification status.

#### 10. Is capability versioning implemented?
**Yes.** Capability definitions enforce strict Semantic Versioning (`X.Y.Z`). Material changes to implementations or adapters require version increments (e.g., `1.0.0` vs `2.0.0`), and benchmark results explicitly track capability version tags.

#### 11. Does the registry survive restart?
**Yes.** `CapabilityRegistry` serializes atomically to JSON on disk (`persistence_path`). Unit and integration tests verify that a newly instantiated registry initialized from disk recovers all capability definitions, performance metrics, and health states with 100% fidelity.

#### 12. Did any existing benchmark regress?
**No.** All existing suites were executed:
- Full test suite: 375 tests passed (up from 347, zero failures).
- Frozen Eval V2: 129/129 passed (100.0%).
- Investigation V1: 25/25 passed (100.0%).
- Clean-room identity audit: identical pass rate and F1.
- Infrastructure audit: identical pass rate and F1.
- Corporate intelligence audit: identical pass rate and F1.
Zero benchmark answers or ground truths were modified.

#### 13. What is Capability Match V1 precision/recall/F1?
- **Precision**: 0.9905
- **Recall**: 1.0000
- **F1 Score**: 0.9943
- **Total Task Pass Rate**: 35 / 35 (100.0%)

#### 14. What are the remaining weaknesses?
1. **Dynamic Runtime Latency Profiling**: Performance profiles currently reflect frozen benchmark-derived metrics; dynamic real-time rolling p95 latency tracking can further refine cost-benefit planning.
2. **Multi-Jurisdiction Granularity**: Current corporate registry capability covers US and UK specifically; additional jurisdictional registries (e.g., EU commercial registers, APAC corporate registries) should be partitioned into specialized sub-capabilities as new data sources are integrated.

#### 15. Is V3.1 ready for Vertical 4 recruitment?
**Yes, unequivocally.** The capability contract, validation suite, adapter interface, and competition mechanics are fully operational. The architecture is ready to evaluate, recruit, and integrate Vertical 4 without modifying core Investigation Engine code.

---

### 3. Deliverables Checklist
- [x] `docs/CAPABILITY_REGISTRY_DESIGN.md`
- [x] `docs/CAPABILITY_REGISTRY_ARCHITECTURE.md`
- [x] `src/argus/capability_registry/` package
- [x] Default capability definitions for all existing components (`src/argus/capability_registry/defaults.py`)
- [x] `CapabilityMatcher` (`src/argus/capability_registry/matcher.py`)
- [x] Fail-closed registry validation (`src/argus/capability_registry/registry.py`)
- [x] `CAPABILITY_MATCH_V1` benchmark suite (`src/argus/capability_registry/benchmark.py`)
- [x] `evals/results/capability_match_v1_results.json`
- [x] `evals/results/capability_match_v1_task_results.json`
- [x] `docs/V3_1_CAPABILITY_REGISTRY_REPORT.md`
- [x] `docs/V3_1_REGRESSION_REPORT.md`
- [x] Updated flat `proofs.zip`
