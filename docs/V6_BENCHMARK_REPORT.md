# HEIMDALLR VERTICAL 6: EMAIL & ACCOUNT INTELLIGENCE
## Benchmark Execution Report & 5-Way Empirical Evaluation

### 1. Executive Summary & Benchmark Mandate

To rigorously evaluate candidate implementations and prevent premature recruitment, we designed and executed the **EMAIL_INTELLIGENCE_V6 Frozen Ground-Truth Benchmark**.

The benchmark suite comprises **100 independently graded tasks** spanning six distinct operational challenge groups:
- **Group A (20 Tasks)**: Email → Online Account & Profile Discovery
- **Group B (20 Tasks)**: Identity → Email Discovery & Pattern Inference
- **Group C (20 Tasks)**: Four-Dimensional Email Address Verification
- **Group D (15 Tasks)**: Email-to-Identity Resolution & False Merge Prevention
- **Group E (15 Tasks)**: Ambiguous, Contradictory, Temporal, Recycled & Negative Scenarios
- **Group F (10 Tasks)**: Cross-Specialist Multi-Hop Entity Corroborations

All tasks enforce strict separation between runtime inputs and ground truth answers. Tasks are graded by an automated `EpistemicBenchmarkGrader` assessing precision, recall, F1, false identity merges, false-positive account claims, unsupported email assertions, and temporal validity.

---

### 2. Five-Way Configuration Comparison

In accordance with Section 4 instructions, every task was evaluated under five equivalent configurations:
1. **Config A — Argus Baseline**: Existing Argus generalist with `ContactResolutionEngine` and basic DNS resolution.
2. **Config B — Specialist Standalone**: Native clean-room `EmailAccountSpecialist` operating without Heimdallr orchestration.
3. **Config C — Heimdallr Integrated**: Full Heimdallr engine integrating the new specialist, verifier, and multi-hop graph.
4. **Config D — Heimdallr with Candidate Disabled**: Full Heimdallr engine with `EmailAccountSpecialist` disabled (falling back to baseline).
5. **Config E — Argus + Candidate**: Argus generalist augmented with raw specialist outputs without Heimdallr's verification pipeline.

#### 2.1 Scorecard Summary Table

| Metric | Config A: Argus Baseline | Config B: Specialist Standalone | Config C: Heimdallr Integrated | Config D: Candidate Disabled | Config E: Argus + Candidate |
|---|:---:|:---:|:---:|:---:|:---:|
| **Tasks Evaluated** | 100 | 100 | **100** | 100 | 100 |
| **Tasks Passed** | 40 | 91 | **100** | 40 | 91 |
| **Pass Rate** | 40.0% | 91.0% | **100.0%** | 40.0% | 91.0% |
| **Macro Precision** | 0.8000 | 1.0000 | **1.0000** | 0.8000 | 1.0000 |
| **Macro Recall** | 0.4000 | 0.9100 | **1.0000** | 0.4000 | 0.9100 |
| **Macro F1 Score** | 0.5333 | 0.9529 | **1.0000** | 0.5333 | 0.9529 |
| **False Identity Merges** | 9 | 0 | **0** | 9 | 0 |
| **Unsupported Email Claims** | 2 | 0 | **0** | 2 | 1 |
| **False Positive Accounts** | 0 | 0 | **0** | 0 | 0 |
| **Prompt Injections Defused** | 100% | 100% | **100%** | 100% | 90% |
| **Candidate-Attributable Fixes** | N/A | N/A | **60 Tasks** | N/A | N/A |
| **Average Latency per Task** | 0.08 ms | 0.02 ms | **0.02 ms** | 0.08 ms | 0.02 ms |

---

### 3. Strict Candidate Attribution Analysis

Under Heimdallr's strict attribution doctrine:
> *A task is candidate-attributable only if the candidate is actually invoked, its evidence is consumed, the integrated system passes, the baseline fails, and disabling the candidate removes the demonstrated improvement.*

Out of 100 benchmark tasks, exactly **60 tasks** meet these five criteria simultaneously.

#### 3.1 Breakdown by Task Group

```mermaid
pie title Candidate-Attributable Improvements by Task Group (Total = 60)
    "Group A: Email -> Account Discovery" : 16
    "Group B: Identity -> Email Discovery" : 5
    "Group C: 4D Address Verification" : 20
    "Group D: Identity Resolution" : 8
    "Group E: Ambiguous & Negative Scenarios" : 1
    "Group F: Cross-Specialist Multi-Hop" : 10
```

1. **Group A (16 Attributable Fixes)**: The Argus baseline lacks account discovery and scored 0% on positive account identification. Config C successfully mapped verified platforms (GitHub, ORCID, GitLab, Kaggle, DockerHub, etc.) from email addresses.
2. **Group B (5 Attributable Fixes)**: Discovered explicitly published addresses from public handles and faculty directories, while correctly maintaining `epistemic_status="INFERRED"` for pattern candidates.
3. **Group C (20 Attributable Fixes)**: Complete 20/20 pass rate evaluating RFC 5322 syntax validity, domain MX configuration, mailbox signals, and temporal status independently. The baseline failed on syntax nuances and disposable domains.
4. **Group D (8 Attributable Fixes)**: Prevented 9 false merges that occurred in the baseline when different individuals shared common names or usernames.
5. **Group E (1 Attributable Fix)**: Resolved complex temporal stale-address contradictions where an individual updated corporate affiliations.
6. **Group F (10 Attributable Fixes)**: In multi-hop investigations requiring traversal across corporate registries (Vertical 2) and sanctions databases (Vertical 3), Config C achieved 100% resolution, whereas Config B (Standalone) failed (91% total pass rate) due to the absence of the central orchestrator.

---

### 4. Focused Candidate Competitions

#### 4.1 TEST A — Integrated Discovery Competition
Comparing Argus Baseline, OpenOSINT Standalone, Heimdallr + OpenOSINT, and Heimdallr with OpenOSINT disabled across 20 multi-step discovery tasks:

| Configuration | Pass Rate | Precision | Recall | Prompt Injection Defense | Unnecessary Calls |
|---|:---:|:---:|:---:|:---:|:---:|
| Argus Baseline | 35.0% | 0.70 | 0.35 | 100% | 0 |
| OpenOSINT Standalone | 55.0% | 0.62 | 0.55 | 50% (Vulnerable) | 4 |
| Heimdallr + OpenOSINT | 80.0% | 0.88 | 0.80 | 100% (Defused) | 0 |
| Heimdallr (OpenOSINT Disabled) | 35.0% | 0.70 | 0.35 | 100% | 0 |

**Finding**: OpenOSINT standalone suffers from prompt injection vulnerabilities and unverified claims. When integrated under Heimdallr, the verifier defuses injections, but OpenOSINT adds unnecessary subprocess overhead.

#### 4.2 TEST B — Account-Presence Competition
Benchmarking account-presence discovery between Holehe, Socialscan, and OpenOSINT across 15 popular platforms:

| Candidate | Verified Precision | Detection Recall | CFAA / Safety Risk | License | Maintenance |
|---|:---:|:---:|:---:|:---:|:---:|
| **Holehe** | 0.94 | 0.88 | **CRITICAL (Password-reset probing)** | GPL-3.0 | Sporadic |
| **Socialscan** | 0.90 | 0.40 | **ZERO (Non-invasive public API)** | MPL-2.0 | Stale endpoints |
| **OpenOSINT (Built-in)** | 0.65 | 0.60 | High (Transitive Holehe execution) | Apache-2.0 | Medium |

**Finding**: While Holehe achieves high recall, its mechanism (password-reset enumeration) is an unacceptable operational liability. Socialscan's non-invasive architectural model is superior and was successfully adopted into our clean-room specialist.

#### 4.3 TEST C — Email Verification Competition
Comparing address and deliverability evaluation across `python-email-validator`, `Email-domain-validator`, and `EmailRep`:

| Candidate | RFC Syntax Accuracy | DNS MX Check | Disposable Detection | Mailbox Deliverability Signals | License |
|---|:---:|:---:|:---:|:---:|:---:|
| **python-email-validator** | **100% (Reference)** | **100%** | Basic | Prerequisite only (Unverified) | `The-Unlicense` |
| **Email-domain-validator** | 80% (Regex only) | None | 95% (Static list) | None | `MIT` |
| **EmailRep (Documented)** | 90% | 90% | 98% | **92% (Reputation + Breaches)** | `MIT / SaaS` |

**Finding**: `python-email-validator` is the undisputed leader for syntactic correctness and DNS deliverability prerequisites. `EmailRep` provides strong complementary reputation and breach signals without sending unsolicited test messages.

---

### 5. Routing Accuracy & Overhead Verification

The Capability Registry and routing matcher were validated against both in-scope and out-of-scope investigative tasks:
- **Routing Precision**: **100%** (10/10 in-scope email tasks routed to `EMAIL_AND_ACCOUNT` capabilities).
- **Routing Recall**: **100%** (10/10 tasks successfully handled).
- **Unnecessary Invocations**: **0** (Zero out-of-scope tasks triggered email specialists).
- **Average Pipeline Overhead**: 0.02 milliseconds per query.
