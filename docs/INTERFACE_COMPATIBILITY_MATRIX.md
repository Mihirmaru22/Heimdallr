# Heimdallr Interface & Compatibility Matrix
**Repository**: `Argus / Heimdallr Core Intelligence Platform`  
**Audit Date**: October 2026  
**Auditor**: Principal Systems Architect & Adversarial Engineering Reviewer  
**Status**: Comprehensive Verification Completed

---

## 1. Executive Summary & Compatibility Assessment

This matrix tracks the data contracts, interface protocols, semantic invariants, and failure boundaries across all major system connections in Heimdallr.

During this audit:
- 12 major cross-component boundaries were systematically audited.
- Critical contract mismatches (e.g. `None` to string `"None"` mutations in `SecurityGateValidator`, `AttributeError` on missing parameters in `EmailIdentityResolutionAdapter`) were discovered, repaired, and regression-tested.
- Overall interface compatibility is certified as **COMPLIANT & SECURE**.

---

## 2. Cross-Component Compatibility Matrix

| # | Producer Component | Consumer Component | Contract Format & Protocol | Validation Point | Failure Behavior & Fallbacks | Compatibility Status | Test Verification |
| :-: | :--- | :--- | :--- | :--- | :--- | :-: | :--- |
| **1** | `InvestigationPlanner` | `CapabilityMatcher` | `InvestigationQuestion` (Pydantic) -> `List[CapabilityCandidate]` | `Matcher.select_minimum_sufficient_set` validates question requirements | Empty list returned; Planner degrades to generic web search | **COMPLIANT** | `tests/capability_registry/test_capability_matcher.py` |
| **2** | `InvestigationPlanner` | `ImplementationSelector` | `CapabilityDefinition` + `Question` -> `CapabilityDefinition` | `Selector.rank_implementations_for_capability` validates status & profile | Returns default capability or highest-ranked active candidate | **COMPLIANT** (Fixed) | `tests/test_engineering_audit_regressions.py::test_implementation_selector_ranking` |
| **3** | `InvestigationOrchestrator` | Specialist Adapters (`CorporateAdapter`) | `dict[str, Any]` (query, entity, jurisdiction) -> `dict[str, Any]` | `CorporateAdapter.execute` extracts `query` and `target_entity` | Returns empty `claims`/`documents` with `NOT_FOUND` status | **COMPLIANT** | `tests/test_corporate_specialist.py` |
| **4** | `InvestigationOrchestrator` | Specialist Adapters (`InfrastructureAdapter`) | `dict[str, Any]` (query, domain, ip) -> `dict[str, Any]` | `InfrastructureSpecialist.execute` parses domain/IP from query | Socket timeout catches connection issues; returns partial DNS | **COMPLIANT** | `tests/test_infrastructure_specialist.py` |
| **5** | `InvestigationOrchestrator` | Specialist Adapters (`IdentityAdapter`) | `dict[str, Any]` (identifier, candidate_records) -> `dict[str, Any]` | `CleanroomIdentitySpecialist.execute` enforces cleanroom boundary | Ambiguous candidates rejected; `is_merged=False` preserved | **COMPLIANT** | `tests/test_cleanroom_identity_specialist.py` |
| **6** | `InvestigationOrchestrator` | Specialist Adapters (`EmailSpecialist`) | `dict[str, Any]` or `str` (query, email, target_identity) -> `dict[str, Any]` | `EmailAccountSpecialist.execute` normalizes str to dict, extracts email | Missing `target_identity` handled safely; `is_merged=False` returned | **COMPLIANT** (Fixed) | `tests/test_engineering_audit_regressions.py::test_email_identity_resolution_adapter_null_safety` |
| **7** | Specialist Adapters | `SecurityGateValidator` | Raw observation payloads -> Sanitized `dict` | `SecurityGateValidator.sanitize_candidate_observation` | Recursive prompt injection scrubbed; HTML defused; types kept | **COMPLIANT** (Fixed) | `tests/test_engineering_audit_regressions.py::test_security_gate_list_of_dict_sanitization` |
| **8** | `SecurityGateValidator` | `EpistemicVerifierEngine` | Sanitized candidate claims -> `VerificationVerdict` | `VerifierEngine.verify_claim` validates against corpus graph | Uncorroborated single sources downgraded to `POSSIBLE` | **COMPLIANT** | `tests/test_verifier.py` |
| **9** | `InvestigationOrchestrator` | `InvestigationState` | Observations, Claims, Evidence -> In-memory DAG | `InvestigationState.add_evidence` checks URL/snippet uniqueness | Duplicates deduplicated; unique `evidence_id` assigned | **COMPLIANT** (Fixed) | `tests/test_engineering_audit_regressions.py::test_evidence_deduplication` |
| **10**| `InvestigationState` | `InvestigationStoppingPolicy` | `InvestigationState` -> `(bool, StopReason, rationale)` | `StoppingPolicy.evaluate` checks critical question resolution | Premature stopping prevented when critical questions are OPEN | **COMPLIANT** (Fixed) | `tests/test_engineering_audit_regressions.py::test_stopping_policy_unresolved_critical_question` |
| **11**| `InvestigationState` | `InvestigationStore` | Pydantic JSON dump -> Disk (`.json` + `_audit.jsonl`) | `InvestigationStore.save_state` sanitizes path & uses atomic tmp | Atomic replacement prevents corruption; audit logs deduplicated | **COMPLIANT** (Fixed) | `tests/test_engineering_audit_regressions.py::test_investigation_store_atomic_write_and_path_safety` |
| **12**| `ArgusRepository` | SQLite Database | Pydantic Models -> Relational Tables | `merge_entities` reconciles duplicate claims & aliases | Corroborated status & maximum confidence strictly preserved | **COMPLIANT** (Fixed) | `tests/test_engineering_audit_regressions.py::test_repository_merge_entities_claim_preservation` |

---

## 3. Detailed Data Contract Audits

### A. Null and Default Value Safety
- **Defect Identified**: `SecurityGateValidator` converted all non-primitive, non-string, non-dict/list values using `str(v)`. Consequently, `None` values became `"None"`. Downstream components expecting optional fields (e.g. `as_of_date: Optional[str] = None`) received string `"None"`, causing date parsers (`datetime.fromisoformat("None")`) to raise runtime exceptions.
- **Remediation**: Added explicit type guards in `SecurityGateValidator.sanitize_candidate_observation` preserving `None`, `bool`, `int`, and `float` as native Python types.

### B. Input Type Normalization
- **Defect Identified**: `EmailAccountSpecialist.execute` expected `inputs: Dict[str, Any]` and immediately called `inputs.get("operation")`. When invoked by callers or legacy pipelines passing a string query (e.g., `"user@example.com"`), an `AttributeError: 'str' object has no attribute 'get'` occurred.
- **Remediation**: Added runtime input normalization `if isinstance(inputs, str): inputs = {"query": inputs}` at the top of `execute`.

### C. Timestamp and Timezone Consistency
- **Audit Finding**: All modules (`state.py`, `models.py`, `db.py`, `repository.py`, `evaluator.py`) standardize on ISO-8601 UTC timestamps generated via `datetime.now(timezone.utc).isoformat()` or `datetime.now(UTC).isoformat()`. No timezone-naive timestamps were detected.

### D. Identifier Normalization & Provenance Stability
- **Audit Finding**: Identifiers across the platform use deterministic prefixed hashes:
  - Claims: `clm_<uuid4_hex[:8]>`
  - Evidence: `evi_<uuid4_hex[:8]>`
  - Questions: `q_<uuid4_hex[:8]>`
  - Executions: `exec_<uuid4_hex[:8]>`
- Provenance links in claims (`evidence_ids: list[str]`) reference valid `evidence_id` keys in `state.evidence` or relational `evidence` tables.

---

## 4. Semantic & Epistemic Compatibility

### Epistemic Status Precedence Invariants
When claims are merged or corroborated across multiple sources (e.g., during `merge_entities` in `ArgusRepository`), the epistemic status must strictly follow the epistemological hierarchy:

$$\text{CONTRADICTED} > \text{CORROBORATED} > \text{SUPPORTED} > \text{INFERRED} > \text{PENDING}$$

- **Defect Repaired**: Prior to remediation, `merge_entities` took `clist[0]` arbitrarily. If the first claim was `PENDING` (confidence 0.5) and the duplicate was `CORROBORATED` (confidence 0.95), the merged claim was erroneously downgraded to `PENDING` (confidence 0.5), silently discarding verified truth.
- **Remediation**: Implemented rigorous status precedence resolution and `confidence = max(confs)` in `ArgusRepository.merge_entities`.
