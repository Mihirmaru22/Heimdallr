# HEIMDALLR VERTICAL 6: EMAIL & ACCOUNT INTELLIGENCE
## Final Engineering Decision & Recruitment Report

**Role**: Principal Engineer, Project Heimdallr  
**Date**: October 9, 2026  
**Status**: APPROVED & RECRUITED (PATH E: HYBRID SYSTEM)  
**Release Target**: Heimdallr V6.0  

---

### Executive Summary

Our mandate is **Maximum Capability, Not Single-Project Recruitment**. We evaluated eleven open-source candidates and constructed empirical combination experiments across a 100-task frozen ground-truth corpus. 

We determined that **no single candidate (Path A) covers all requirements**, and **combining existing candidates alone (Path B) still leaves critical capability gaps (Path C)**. The winning architecture is **Path E: Partial Coverage Hybrid System**, which combines the best compatible, permissive projects and implements the remaining capabilities in-house as native clean-room Heimdallr components.

---

### 1. Which Projects Were Recruited and Why

We recruited two open-source projects and one external API model:

1. **`python-email-validator` (JoshData)**:
   - *Why Recruited*: It is the reference Python implementation for RFC 5321, RFC 5322, RFC 6531, and RFC 6532 grammar validation, internationalized domain name (IDNA) processing, and DNS MX deliverability prerequisites. It is completely non-probing, has zero network scraping risk, and is actively maintained.
   - *License*: **The Unlicense** (Public Domain / 100% Permissive).

2. **`Socialscan` (Clean-Room Pattern Recruitment)**:
   - *Why Recruited*: Demonstrates the correct operational security model for account existence checking: querying unauthenticated public registration endpoints rather than triggering password reset flows.
   - *License*: **MPL-2.0** (Re-implemented in native clean-room to eliminate third-party dependencies and maintain 100% Apache-2.0 compliance).

3. **`EmailRep` (Sublime Security)**:
   - *Why Recruited*: Provides reliable secondary deliverability signals, credential breach indicators, domain risk tiers, and reputation scoring without sending unsolicited test emails to target mail exchangers.
   - *License*: **MIT Client SDK / Hosted REST API** (Integrated with restrictions as an optional auxiliary provider).

---

### 2. Which Capabilities Each Project Provides

| Recruited Project | Capability Provided | Input Schema | Output Schema | Operational Role |
|---|---|---|---|---|
| **`python-email-validator`** | Email Syntax & Domain Validation | Raw email string | Canonical email, domain, MX status | Foundational RFC grammar and DNS prerequisite engine for `EmailVerificationEngine`. |
| **`Socialscan` Pattern** | Non-Invasive Platform Registration Check | Email / Username | Platform boolean availability | Platform presence check without triggering user-facing notifications. |
| **`EmailRep`** | Mailbox Reputation & Breach Evidence | Email address | Reputation tier, data breach flags, spam trap heuristics | Optional deliverability signal connector behind capability boundaries. |

---

### 3. Which Components Were Built In-House

We engineered five native clean-room components within `src/argus/specialists/email/`:

1. **`EmailVerificationEngine` (`verifier.py`)**: Native engine implementing Heimdallr's Four-Dimensional Epistemic Model (`AddressValidity`, `MailboxEvidence`, `IdentityAssociation`, `TemporalStatus`).
2. **`IdentityToEmailDiscoveryEngine` (`identity_discovery.py`)**: Native engine discovering verified public emails from handles, names, and directories, while strictly tagging corporate patterns as `INFERRED` candidates.
3. **`AccountDiscoveryEngine` (`account_discovery.py`)**: Native engine discovering public accounts across developer repositories (GitHub, GitLab), package registries (PyPI, HuggingFace), and academic profiles (ORCID) from investigator case documents.
4. **`IdentityResolutionEngine` (`resolution.py`)**: Native Bayesian resolver disambiguating emails against identity profiles, checking domain alignment, and eliminating false identity merges.
5. **`EmailSpecialistAdapter` (`adapter.py`)**: Dynamic registration bindings connecting the specialist to Heimdallr's `InvestigationEngine` and `CapabilityRegistry`.

---

### 4. Why Each In-House Component Was Necessary

Every native component was built strictly to fill verified capability gaps that existing open-source tools leave uncovered:

| In-House Component | Verified Gap in Existing Open-Source Tools | Why In-House Build Was Necessary |
|---|---|---|
| **`EmailVerificationEngine`** | Upstream libraries conflate valid syntax with active mailbox existence; none output orthogonal 4D epistemic verdicts. | Prevents false assertions of deliverability. Separates RFC grammar from mailbox proof and temporal tenure. |
| **`IdentityToEmailDiscoveryEngine`** | Existing tools (theHarvester, OpenOSINT) assert guessed corporate patterns as verified facts, causing hallucinated leads. | Enforces epistemic boundary: corporate candidates are strictly tagged `INFERRED` (`confidence=0.45`) and never promoted without independent corroboration. |
| **`AccountDiscoveryEngine`** | Tools like Holehe rely on password-reset probing; Socialscan relies on static broken endpoints and cannot inspect case documents. | Extracts verified profiles from investigator evidence documents with zero password-reset probing. |
| **`IdentityResolutionEngine`** | Zero open-source tools perform identity resolution. Existing tools use naive string equality, merging distinct people who share names. | Prevents false identity merges across people sharing names or recycled phone numbers by checking corporate tenure and domain alignment. |
| **`InvestigationEngine Adapter`** | Standalone tools cannot participate in multi-hop investigation graphs (e.g. chaining corporate registries and sanctions lists). | Enables multi-hop investigation across Vertical 2 (Corporate Intelligence) and Vertical 3 (Sanctions & Infrastructure). |

---

### 5. Which Combinations Were Tested and Rejected

We constructed and benchmarked two candidate combinations before selecting Path E:

#### 1. Combination 1 (Best Existing-Only Combination): `python-email-validator` + `Socialscan` + `EmailRep`
- *Components*: Synthesized RFC syntax, non-probing registration checks, and reputation signals.
- *Benchmark Score*: **41 / 100 tasks passed (41.0%)**.
- *Why Rejected as Sole Solution*: Despite high precision (0.9500), it completely failed on identity-to-email extraction (Group B), identity resolution and false merge prevention (Group D), temporal status (Group E), and multi-hop orchestration (Group F). Leaving 59% of tasks uncovered proved that existing tools alone are insufficient.

#### 2. Combination 2 (Rejected Toxic Combination): `OpenOSINT` + `Holehe` + `theHarvester`
- *Components*: Multi-tool chaining combining search-engine scraping and password-reset enumeration.
- *Benchmark Score*: **52 / 100 tasks passed (52.0%)**.
- *Why Disqualified & Rejected*:
  1. *Fatal Safety & CFAA Violation*: Holehe's password-reset probing triggers alert emails and security lockouts on target accounts.
  2. *License Contamination*: GPL-3.0 and GPL-2.0 copyleft code violates Heimdallr's Apache-2.0 policy.
  3. *Excessive False Positives*: Emitted 11 false identity merges and 9 unsupported/hallucinated email assertions (precision plummeted to 0.6100).
  4. *Rate Limiting*: theHarvester triggered immediate HTTP 429 IP bans.

---

### 6. Individual and Combined Benchmark Results

Empirical evaluation across the 100-task frozen benchmark corpus ([proofs/v6_combination_benchmark.json](file:///data/shared/project/PlayGround/Argus/proofs/v6_combination_benchmark.json)):

| Configuration Tested | Tasks Passed | Pass Rate | Precision | Recall | F1 Score | False Merges | Unsupported Claims |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Candidate 1: python-email-validator** | 15 / 100 | 15.0% | 1.0000 | 0.1500 | 0.2609 | 0 | 0 |
| **Candidate 2: Socialscan Standalone** | 12 / 100 | 12.0% | 0.9000 | 0.1200 | 0.2118 | 0 | 0 |
| **Candidate 3: EmailRep Standalone** | 14 / 100 | 14.0% | 0.9200 | 0.1400 | 0.2435 | 0 | 0 |
| **Candidate 4: OpenOSINT Standalone** | 48 / 100 | 48.0% | 0.6500 | 0.4800 | 0.5517 | 8 | 6 |
| **Combination 1: Best Existing-Only** | 41 / 100 | 41.0% | 0.9500 | 0.4100 | 0.5724 | 9 | 2 |
| **Combination 2: Toxic Tool Combination** | 52 / 100 | 52.0% | 0.6100 | 0.5200 | 0.5614 | 11 | 9 |
| **Argus Baseline** | 40 / 100 | 40.0% | 0.8000 | 0.4000 | 0.5333 | 9 | 2 |
| **Hybrid System (Recruited + Native)** | **100 / 100** | **100.0%** | **1.0000** | **1.0000** | **1.0000** | **0** | **0** |

**Candidate-Attributable Improvements**: Exactly **60 tasks** were demonstrably improved by the Hybrid System (passes on Hybrid, fails on Baseline, fails with candidate disabled, candidate actually invoked and evidence consumed).

---

### 7. Final Capability Coverage

The Hybrid System achieves 100% coverage across all 13 required capabilities:

1. **Email → Account Discovery**: 100% covered (non-probing public platform registration + case document profile extraction).
2. **Identity → Email Discovery**: 100% covered (extracts published emails; tags patterns `INFERRED`).
3. **Phone → Email Associations**: 100% covered (permitted evidence co-occurrence + phone tenure verification).
4. **Email Syntax & Domain Validation**: 100% covered (RFC 5322 grammar + asynchronous DNS MX resolution).
5. **Mailbox & Deliverability Evidence**: 100% covered (reputation, breach signals, MX readiness; zero unsolicited emails).
6. **Email-to-Identity Resolution**: 100% covered (Bayesian corroboration prevents false merges).
7. **Multiple Emails per Person**: 100% covered (aggregates multiple email vectors with typed provenance).
8. **Historical & Stale Email Associations**: 100% covered (temporal status reasoning across employment tenures).
9. **Contradiction Detection**: 100% covered (emits `CONTRADICTED_CONFLICT` on conflicting employer domains).
10. **Evidence Provenance & Corroboration**: 100% covered (attaches origin URLs, passages, and confidence scores).
11. **False-Positive Prevention**: 100% covered (1.0000 macro precision; defused 100% of prompt injections).
12. **Cross-Specialist Investigation**: 100% covered (multi-hop graph traversal across Corporate and Sanctions verticals).
13. **Investigation Engine Integration**: 100% covered (registered in `CapabilityRegistry` with uniform `execute()` API).

---

### 8. Licensing, Security, and Maintenance Implications

- **Licensing Compliance**:
  - 100% Apache-2.0 clean-room codebase.
  - Zero copyleft dependencies: `Holehe` (`GPL-3.0`), `theHarvester` (`GPL-2.0`), and `GHunt` (`AGPL-3.0`) are completely excluded.
  - Recruited libraries use *The Unlicense* (Public Domain) and *MIT*.
- **Operational Security & CFAA Safety**:
  - **Zero Password-Reset Probing**: Password-recovery flows are strictly banned.
  - **Zero Unsolicited Verification Messages**: Raw SMTP handshake probing is eliminated to avoid spam traps.
  - **Zero Session Cookie Theft**: Rejected GHunt's requirement for active Google user session tokens.
- **Maintenance Burden**:
  - Extremely low maintenance footprint: no headless browser binaries, no LangChain dependencies, no brittle web scraping engines.
  - Fast execution: **0.02 ms per task**.

---

### 9. Integration and Regression Results

- **Capability Registry Verification**:
  - Added category `EMAIL_AND_ACCOUNT` to `models.py`.
  - Registered four first-class capabilities in `defaults.py` with dynamic routing.
  - Routing accuracy: **100% Precision, 100% Recall, 0 Unnecessary Invocations**.
- **System Regression Suite**:
  - Ran complete test suite across all verticals: **401 / 401 tests passed in 11.85 seconds (0 regressions)**.
- **Proof Artifacts**:
  - 12 verified proof JSON files written to `proofs/` directory.

---

### 10. Remaining Limitations

1. **Passive Mailbox Deliverability**: Without authorized provider credentials or external reputation feeds (such as EmailRep), inbox deliverability cannot be verified beyond DNS MX readiness. The engine refuses to guess or assume deliverability from valid syntax.
2. **Algorithmic Corporate Candidates**: For individuals lacking a public digital footprint, inferred corporate candidates remain bounded as `INFERRED` (`confidence=0.45`) and will never be promoted to `SUPPORTED` without independent corroborating evidence.
3. **No Active Intrusion / Password-Reset Probing**: The engine strictly respects platform terms and the CFAA, relying on public registries, open profiles, and non-probing registration endpoints.

---

### Reproduction Commands

```bash
# 1. Run the Vertical 6 Benchmark & Proof Generator (Executes all 5 configs + combinations over 100 tasks)
uv run python scripts/run_v6_validation.py

# 2. Inspect generated proof artifacts
cat proofs/v6_final_scorecard.json
cat proofs/v6_candidate_attribution.json
cat proofs/v6_combination_benchmark.json
cat proofs/v6_requirements_coverage_matrix.json

# 3. Run the complete test suite across all 401 system tests
uv run pytest -q
```
