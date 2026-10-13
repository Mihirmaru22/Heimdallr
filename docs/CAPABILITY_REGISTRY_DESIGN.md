# Heimdallr V3.1: Capability Registry Design Specification
## Formalizing the Specialist Intelligence Layer

### 1. Architectural Motivation & Executive Summary

In Heimdallr V1 and V2, specialists (Identity Specialist, Infrastructure Specialist, Corporate Specialist) and general research capabilities (Argus) were integrated into autonomous workflows. However, specialist dispatch was tied directly to hardcoded specialist identifiers (`"identity"`, `"corporate"`, `"infrastructure"`). 

Heimdallr V3.1 introduces the **Capability Registry**, a decoupled, formal abstraction layer that separates:
1. **Abstract Capability**: What type of intelligence or operation is needed (e.g., `identity_resolution`, `infrastructure_discovery`, `corporate_registry_intelligence`, `general_web_research`).
2. **Concrete Implementation**: The executable component or probe that fulfills that capability (e.g., `impl_identity_probe_specialist_v1`, `impl_challenger_identity_specialist_v2`, `impl_infrastructure_probe_specialist_v1`, `impl_corporate_registry_specialist_v1`, `impl_argus_generalist_v1`).

By decoupling capabilities from implementations:
- The **Investigation Engine** and **InvestigationPlanner** plan based on **Evidence Requirements** and **Question Types**, rather than hardcoded specialist names.
- Multiple implementations of the same capability can coexist, compete, and be benchmarked simultaneously.
- Runtime health lifecycle states (`AVAILABLE`, `DEGRADED`, `UNAVAILABLE`, `DISABLED`, `QUARANTINED`) prevent cascading failures and allow graceful fallbacks.
- Epistemic authority contracts are explicitly enforced: specialist outputs remain **candidate-producing observations**, while Argus/Verifier retains authoritative claim confirmation.

---

### 2. Core Concepts: Capability vs Implementation

```
+-----------------------------------------------------------------------------------+
|                               INVESTIGATION ENGINE                                |
|   InvestigationQuestion -> Evidence Requirements -> CapabilityMatcher             |
+-----------------------------------------------------------------------------------+
                                          |
                                          v (Queries required capability)
+-----------------------------------------------------------------------------------+
|                                CAPABILITY REGISTRY                                |
|   Capability: identity_resolution                                                 |
|   Category: IDENTITY                                                              |
|   Evidence: [Social handle, PGP key, Developer profile, Keybase proof]            |
+-----------------------------------------------------------------------------------+
             |                                              |
             v (Registered Impl 1)                          v (Registered Impl 2)
+---------------------------------------+      +------------------------------------+
| Implementation:                       |      | Implementation:                    |
| impl_identity_probe_specialist_v1     |      | impl_challenger_identity_spec_v2   |
| Provider: CleanRoom Specialist Labs   |      | Provider: Challenger Labs OpenOSINT|
| Version: 1.0.0                        |      | Version: 2.0.0                     |
| F1 Score: 0.971 (Benchmark Observed)  |      | F1 Score: 0.980 (Benchmark Observed)|
| Epistemic Nature: CANDIDATE           |      | Epistemic Nature: CANDIDATE        |
+---------------------------------------+      +------------------------------------+
```

#### Invariant: No Implied Authority
Specialist probes must **NEVER** become authoritative simply by virtue of registration. The output schema strictly declares `authoritative: False` and `epistemic_nature: CANDIDATE` or `OBSERVATION`. Verification remains the sole purview of Argus and the Verifier Engine.

---

### 3. Capability Contract Specification

The capability contract is enforced by strongly typed Pydantic models in `src/argus/capability_registry/models.py`.

#### 3.1 Field Definitions
- **`capability_id`** (`str`): Unique identifier for the abstract capability (e.g., `identity_resolution`).
- **`name`** (`str`): Human-readable capability name.
- **`description`** (`str`): High-level operational scope and description.
- **`version`** (`str`): Semantic version (`MAJOR.MINOR.PATCH`).
- **`category`** (`CapabilityCategory`): Primary functional category.
- **`status`** (`HealthStatus`): Runtime health state (`AVAILABLE`, `DEGRADED`, `UNAVAILABLE`, `DISABLED`, `QUARANTINED`).
- **`provider`** (`str`): Author or organization providing the implementation.
- **`implementation_id`** (`str`): Unique identifier for the specific implementation (e.g., `impl_identity_probe_specialist_v1`).
- **`input_schema`** (`CapabilityInputSchema`): Declares required fields, optional fields, and type annotations.
- **`output_schema`** (`CapabilityOutputSchema`): Declares output fields, epistemic nature (`CANDIDATE`, `OBSERVATION`, `CLAIM`, `VERIFIED_FACT`), and authority flag (`authoritative=False`).
- **`question_types`** (`list[str]`): Types of investigation questions this capability can resolve.
- **`supported_operations`** (`list[str]`): Low-level operations supported (e.g., `DNS_LOOKUP`, `CT_LOG_SEARCH`, `OFFICER_EXTRACTION`).
- **`evidence_types`** (`list[str]`): Types of evidence this capability discovers or emits.
- **`epistemic_behavior`** (`str`): Plain English description of candidate boundaries and verification requirements.
- **`temporal_behavior`** (`str`): Support for temporal reasoning (point-in-time, as-of dating, historical state).
- **`jurisdictions`** (`list[str]`): ISO country codes or jurisdictional scopes supported (e.g., `["GLOBAL"]`, `["GB"]`, `["US"]`).
- **`entity_types`** (`list[str]`): Supported entity classes (e.g., `PERSON`, `ORGANIZATION`, `DOMAIN`, `IP_ADDRESS`).
- **`dependencies`** (`list[str]`): Declared upstream capabilities or services required.
- **`limitations`** (`list[str]`): Documented boundaries and blind spots.
- **`failure_modes`** (`list[str]`): Known failure behaviors under edge conditions.
- **`cost_model`** (`CostModel`): Unit cost per query/operation in USD and latency estimates.
- **`performance_profile`** (`PerformanceProfile`): Benchmark-observed precision, recall, F1, accuracy, and failure rate.
- **`security_profile`** (`SecurityProfile`): Egress requirements, rate limiting, and sandbox constraints.
- **`license_metadata`** (`LicenseMetadata`): License type, clean-room status, commercial compatibility, and restrictions.
- **`benchmark_metadata`** (`dict[str, Any]`): Benchmark identifier, version, and measurement metadata.

---

### 4. Capability Categories & Question Taxonomy

#### 4.1 Extensible Category Hierarchy
The system initializes with 9 standard categories:
- `GENERAL_RESEARCH`: Unconstrained web and document corpus research (Argus).
- `IDENTITY`: Persona, handle, developer profile, and email correlation.
- `INFRASTRUCTURE`: DNS, TLS/SAN, IP attribution, certificate transparency, and subdomain asset graphs.
- `CORPORATE`: Official statutory registries, corporate filings, officer rosters, shareholdings, and parent/subsidiary hierarchies.
- `DOCUMENT_INTELLIGENCE`: Deep PDF/HTML extraction, table parsing, and layout extraction.
- `VERIFICATION`: Multi-source corroboration, epistemic state validation, and primary document grounding.
- `ENTITY_RESOLUTION`: Disambiguation, entity merging, canonicalization, and alias linking.
- `TEMPORAL_REASONING`: Point-in-time state reconstruction, officer tenure tracking, and historical timeline analysis.
- `CONTRADICTION_ANALYSIS`: Discrepancy detection between competing sources, restatements, and amendments.

#### 4.2 Question Type Taxonomy
Capabilities declare support for standard question types:
- **Identity**:
  - `WHO_IS_THIS_IDENTIFIER`: Correlate an online username or handle to real-world personas.
  - `IS_THIS_PROFILE_THE_SAME_PERSON`: Validate handle co-ownership across disparate networks.
  - `FIND_PUBLIC_PROFILE_ASSOCIATIONS`: Enumerate public code repositories, commits, and profiles.
- **Infrastructure**:
  - `WHAT_INFRASTRUCTURE_IS_ASSOCIATED`: Map corporate domains and technical assets.
  - `WHAT_HOSTNAMES_EXIST`: Discover subdomains via Certificate Transparency and DNS.
  - `WHAT_CERTIFICATES_REFERENCE_ENTITY`: Discover SAN entries referencing brand entities.
  - `IS_THIS_ASSET_LIKELY_RELATED`: Disambiguate owned assets from shared CDN/SaaS infrastructure.
- **Corporate**:
  - `WHAT_IS_THE_LEGAL_ENTITY`: Resolve informal trade names to registered legal entity names.
  - `WHO_ARE_THE_OFFICERS`: Extract active and resigned directors, CISOs, CEOs, and secretaries.
  - `WHO_OWNS_THIS_ENTITY`: Identify ultimate parent organizations and beneficial ownership.
  - `WHAT_SUBSIDIARIES_EXIST`: Enumerate statutory subsidiaries and international branches.
  - `WHAT_ACQUISITIONS_OCCURRED`: Discover historical M&A dates and divestitures.
- **General Research**:
  - `FIND_PUBLIC_INFORMATION`: Unstructured discovery across press releases, websites, and articles.
  - `DISCOVER_ENTITY`: Initial reconnaissance on newly identified targets.
  - `FIND_SUPPORTING_DOCUMENT`: Locate secondary documents and industry reports.
  - `FIND_PRIMARY_SOURCE`: Identify original primary citations and disclosures.

---

### 5. Benchmark Performance Profiles & Observational Integrity

Performance metadata reflects **empirical, benchmark-derived observations**, never unbounded claims.

#### Structure:
```python
PerformanceProfile(
    accuracy=0.975,
    precision=0.960,
    recall=0.985,
    f1=0.971,
    evidence_correctness=0.950,
    epistemic_accuracy=1.000,
    temporal_accuracy=0.920,
    cost=0.00007,
    runtime_sec=0.00007,
    failure_rate=0.025,
    benchmark_id="EVAL_V2_1_IDENTITY_AUDIT",
    benchmark_version="2.1.0",
    measurement_date="2026-10-07T12:00:00Z",
    scope="BENCHMARK_OBSERVED"
)
```

Rules:
1. Every metric must reference a specific `benchmark_id` and `benchmark_version`.
2. The scope is explicitly marked `BENCHMARK_OBSERVED`.
3. Marketing or qualitative claims (e.g., "100% accurate identity tool") are rejected by registry validation.

---

### 6. License, Clean-Room, & Recruitment Metadata

To protect intellectual property integrity and prepare for Vertical recruitment, every capability declaration includes `LicenseMetadata`:
- `license`: SPDX identifier (e.g., `Apache-2.0`, `MIT`, `Proprietary`).
- `license_status`: `APPROVED`, `RESTRICTED`, `REFERENCE_ONLY`, `REJECTED`, `UNKNOWN`.
- `source_type`: `IN_HOUSE`, `CLEAN_ROOM_REIMPLEMENTATION`, `UPSTREAM_OPEN_SOURCE`, `COMMERCIAL_API`.
- `repository`: Source code repository URI.
- `version`: Release tag or semantic version.
- `commit`: Git SHA commit reference.
- `clean_room_status`: Boolean indicator of independent clean-room implementation.
- `commercial_compatibility`: Boolean flag for commercial deployment.
- `restrictions`: Explicit lists of use constraints.

---

### 7. Fail-Closed Validation Rules

The registry enforces strict fail-closed validation on startup and registration:
1. **Unique Identifiers**: `capability_id` and `implementation_id` must be non-empty and well-formed.
2. **Duplicate Detection**: Registering an identical `implementation_id` without explicit `overwrite=True` raises `RegistryValidationError`.
3. **SemVer Validation**: `version` must match strict semantic versioning `X.Y.Z`.
4. **Epistemic Invariant**: Definitions that declare `authoritative=True` while simultaneously declaring `epistemic_nature=CANDIDATE` or `OBSERVATION` are rejected immediately.
5. **License Compliance**: Implementations with `license_status=REJECTED` cannot be registered.
6. **Self-Dependency Rejection**: Capabilities cannot declare dependencies on themselves.
7. **Schema Completeness**: `input_schema` and `output_schema` must be populated.
