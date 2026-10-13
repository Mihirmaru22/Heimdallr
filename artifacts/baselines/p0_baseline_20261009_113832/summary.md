# Heimdallr P0 Reproducible System Baseline Report

> **Run ID**: `p0_baseline_20261009_113832`  
> **Timestamp (UTC)**: `2026-10-09T11:38:51.792736+00:00`  
> **Git Commit**: `56c62b5008219f558c89a79c34cd1bf5ec0f4d79`  
> **Git Branch**: `experiment/challenger-recruitment`  
> **Working Tree**: `DIRTY (389 uncommitted changes)`  
> **Execution Mode**: `offline_frozen`  
> **Model Provider**: `deterministic_eval_offline` (`OFFLINE_FROZEN_CORPUS`)  

---

## 1. Verified System Status

| Dimension | Measured Value | Verification Source |
| :--- | :---: | :--- |
| **Unit & Regression Suite** | `440 passed / 440 total (15.57s)` | pytest execution |
| **Frozen Benchmark Suite** | `Eval V2 Frozen (120 tasks)` | `data/evals/v2/benchmark_tasks.json` |
| **Ground Truth Isolation** | `ENFORCED (GroundTruthAccessGuard)` | All 13 expected_output attributes blocked during execution |
| **Run Determinism** | `100.0% Agreement (0 discrepancies)` | 2-run repeat comparison |
| **Working Tree Cleanliness** | `DIRTY` | `git status --porcelain` |

---

## 2. Eval V2 Frozen Benchmark (120 Tasks) — Multi-Configuration Specialist Ablations

Evaluates the core system alone vs. standalone specialists vs. integrated specialists vs. cumulative milestones vs. Heimdallr V2.

| Configuration | Pass Rate | Passed / Total | Entity F1 | Field Acc | Evidence Corr | Critical Fails | Runtime |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Argus Baseline (Specialists Disabled)** | **`0.0%`** | `0 / 120` | `20.3%` | `45.0%` | `99.2%` | `1` | `0.216s` |
| **Identity Specialist (Standalone)** | **`12.5%`** | `15 / 120` | `20.3%` | `16.7%` | `98.3%` | `2` | `0.046s` |
| **Argus + Identity (Integrated)** | **`8.3%`** | `10 / 120` | `19.3%` | `18.8%` | `98.3%` | `2` | `0.219s` |
| **Infrastructure Specialist (Standalone)** | **`12.5%`** | `15 / 120` | `20.0%` | `18.8%` | `98.3%` | `2` | `0.073s` |
| **Argus + Infrastructure (Integrated)** | **`13.3%`** | `16 / 120` | `22.8%` | `25.4%` | `98.3%` | `2` | `0.221s` |
| **Corporate Specialist (Standalone)** | **`12.5%`** | `15 / 120` | `20.9%` | `24.6%` | `99.2%` | `1` | `0.162s` |
| **Argus + Corporate (Integrated)** | **`4.2%`** | `5 / 120` | `19.2%` | `30.0%` | `99.2%` | `1` | `0.23s` |
| **Cumulative Milestone 0 (Argus Core)** | **`5.0%`** | `6 / 120` | `14.0%` | `20.8%` | `98.3%` | `2` | `0.253s` |
| **Cumulative Milestone 1 (Argus + Id)** | **`4.2%`** | `5 / 120` | `15.2%` | `22.5%` | `98.3%` | `2` | `0.253s` |
| **Cumulative Milestone 2 (Argus + Id + Infra)** | **`0.0%`** | `0 / 120` | `11.7%` | `27.1%` | `98.3%` | `2` | `0.257s` |
| **Cumulative Milestone 3 (Full Stack)** | **`0.0%`** | `0 / 120` | `13.4%` | `47.1%` | `99.2%` | `1` | `0.257s` |
| **Heimdallr V2 (Investigation Engine)** | **`100.0%`** | `120 / 120` | `99.9%` | `100.0%` | `100.0%` | `0` | `0.381s` |

---

## 3. Investigation of the Heimdallr V2 120/120 Score

A deep audit was conducted on how Heimdallr V2 achieves 120/120 (100.0%) on the Eval V2 frozen benchmark:

1. **Execution Path & Input Isolation**:
   - `run_investigation_v2_task` receives only `task.query` and `task.known_context`.
   - `GroundTruthAccessGuard` wraps the execution block and raises `EvaluatorGroundTruthAccessError` if any attribute of `task.expected_output` is read.
   - Tracing confirmed **zero property accesses** to `task.expected_output` occurred during the execution phase.
2. **Mechanism of High Score**:
   - The runner formulates targeted corpus queries based on the task category and query string (e.g. mapping `Consortium Vehicle {idx}` to corresponding SEC / UK Companies House synthetic documents in `CORPUS_V2_REGISTRY`).
   - The in-memory registry contains complete synthetic documents matching every benchmark task scenario.
   - Discovered triples and evidence snippets precisely match what the deterministic grader expects.
3. **Caveat on Real-World Research Capability**:
   - **This 100% score is on the frozen in-memory corpus (`CORPUS_V2_REGISTRY`).**
   - It verifies that the investigation engine's hypothesis loop, specialist dispatch, and relationship extractors function correctly against known documents.
   - **It does NOT prove 100% real-world research capability on open, dirty, live-web intelligence targets.**

---

## 4. Distinct Benchmark Comparison: Eval V1 Historical Core Suite (11 Tasks)

To contrast in-memory synthetic performance with real pipeline extraction, the end-to-end Argus pipeline was executed against the **Eval V1 Core Suite** (11 tasks, real neural System 1 triage, multi-tier crawler mock, and worker/verifier pipeline):

- **Suite Name**: `Eval V1 Historical Core Suite (11 tasks)`
- **Task Pass Rate**: `45.5%` (5 / 11 tasks passed)
- **Field Accuracy**: `50.0%` *(Contrasts with Eval V2 Argus baseline 0.0%: Eval V1 evaluates simple company profiles like Ford and Tesla with partial matching, whereas Eval V2 tests multi-hop cross-domain chains)*
- **Entity Precision**: `13.5%` *(Bottleneck: background entity noise without specialist scoping)*
- **Entity Recall**: `71.2%`
- **Evidence Correctness**: `92.5%`
- **Unsupported Claim Rate**: `7.5%`
- **Contradiction Detection**: `90.9%`
- **Wall-Clock Duration**: `514.2 seconds` (~8.5 min total, avg 46.75 sec/task)

---

## 5. Cost & Performance Instrumentation

- **Actual Production Model Tokens**: `NOT INSTRUMENTED` (Offline deterministic mock/in-memory evaluator).
- **Actual Production Model Dollar Cost**: `NOT INSTRUMENTED` (No live billing API metadata).
- **Tokenizer Proxy Tokens**: `205,800 tokens` (`$0.3087`).
- **Per-Task Average Latency**: `0.0032 sec`.

---

## 6. Artifact Index

All machine-readable deliverables are located in:
`/data/shared/project/PlayGround/Argus/artifacts/baselines/p0_baseline_20261009_113832`

- `manifest.json`: Commit SHA, branch, working-tree status, dependency hashes, configuration fingerprint.
- `environment.json`: Python build, CPU/OS details, sanitized environment variables.
- `test_results.json`: Pytest 440-test pass/fail counts and status.
- `benchmark_results.json`: Aggregate metrics across all 12 specialist ablation configurations.
- `task_results.json`: Complete 120-task results across all 12 configurations with observed outputs, severity, and scoring.
- `performance.json`: Wall-clock timings, query counts, isolation audit, and repeat determinism audit.
- `limitations.json`: Enumeration of uninstrumented metrics and offline blocked suites.
- `summary.md`: This executive report.
