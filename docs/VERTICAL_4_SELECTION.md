# VERTICAL 4 SELECTION: FORENSIC CAPABILITY GAP ANALYSIS
**Evidence-Driven Selection of Heimdallr's Fourth Intelligence Vertical**
**Repository:** Argus / Heimdallr V3.2
**Date:** 2026-10-08
**Auditor / Architect:** Antigravity Autonomous Systems

---

## Executive Summary

In accordance with Section 10 of the V3.2 specification, Vertical 4 is not selected based on popularity, star count, or arbitrary preference. It is selected through systematic examination of measured intelligence gaps from:
1. **Heimdallr Eval V2 & V2.1 Residual Failures** ([`docs/EVAL_V2_1_FAILURE_ANALYSIS.md`](file:///data/shared/project/PlayGround/Argus/docs/EVAL_V2_1_FAILURE_ANALYSIS.md))
2. **Investigation Engine V1 Failure Taxonomy** ([`docs/HEIMDALLR_FAILURE_DRIVEN_ENGINEERING.md`](file:///data/shared/project/PlayGround/Argus/docs/HEIMDALLR_FAILURE_DRIVEN_ENGINEERING.md))
3. **Capability Registry V3.1 Coverage Map** ([`docs/CAPABILITY_REGISTRY_ARCHITECTURE.md`](file:///data/shared/project/PlayGround/Argus/docs/CAPABILITY_REGISTRY_ARCHITECTURE.md))
4. **Adversarial Corporate & Shell Evasion Traps** (`v2_cat10_task04`, `v2_cat22_task04`)

**Final Selection:** **`sanctions_and_beneficial_ownership`** (International Sanctions Lists, Politically Exposed Persons (PEPs), and Cross-Border Offshore Trusts / Shell Companies).

---

## 1. Measured Capability Gaps in the Current Stack

Heimdallr V3.1 possesses four verified intelligence capabilities:

| Existing Capability | Incumbent Implementation | Operational Scope | Blind Spot / Measured Failure Boundary |
| :--- | :--- | :--- | :--- |
| **`corporate_registry_intelligence`** | `CorporateRegistrySpecialist` (`v1.0.0`) | SEC EDGAR (US) & Companies House (GB) | Completely blind to offshore shell entities (BVI, Cayman, Panama, Cyprus), trusts, and international sanctions flags. |
| **`infrastructure_discovery`** | `InfrastructureProbeSpecialist` (`v1.0.0`) | DNS, CT log SAN, WHOIS, ASN | Only observes technical network topology; cannot determine if an entity is sanctioned or owned by an oligarch. |
| **`identity_resolution`** | `IdentityProbeSpecialist` (`v1.0.0`) / `ChallengerIdentity` (`v2.0.0`) | GitHub/GitLab handles, PGP keys, commit emails | Only resolves public software developers; lacks PEP rosters, financial crime notices, and sanctions aliases. |
| **`general_web_research`** | `ArgusGeneralist` (`v1.0.0`) | Unstructured web crawl & search | High noise, highly susceptible to adversarial syndication rings, cannot verify regulatory sanctions supremacy. |

### The Forensic Failure Evidence:
In [`docs/HEIMDALLR_FAILURE_DRIVEN_ENGINEERING.md`](file:///data/shared/project/PlayGround/Argus/docs/HEIMDALLR_FAILURE_DRIVEN_ENGINEERING.md#L143-L162), the forensic breakdown of persistent evaluation failures proved:
- **Developer / Code Intelligence:** 0 residual failures stemmed from code repository voids.
- **Financial Balance Sheets:** 0 residual failures stemmed from missing accounting ratios (10-K already covers Exhibit 21 and statements).
- **Offshore & Sanctions Void:** The critical failure boundary occurred on tasks where target entities operated through offshore shell companies (Panama, BVI, Cyprus) or concealed beneficial owners on international sanctions lists (OFAC SDN, EU Consolidated, UK OFSI).

---

## 2. Candidate Domain Options Evaluated

We evaluated three potential domains for Vertical 4:

### Option A: Code Repository & Software Dependency Intelligence
- *Scope:* GitHub/GitLab commit graphs, SBOM analysis, package registry provenance.
- *Marginal Value:* **LOW.** Identity Specialist already extracts developer commits, PGP signing keys, and repository contributor metadata. Does not solve any persistent benchmark failures.

### Option B: Patent & Intellectual Property Intelligence
- *Scope:* USPTO, EPO, WIPO patent filings and patent assignment graphs.
- *Marginal Value:* **MODERATE.** Useful for technological asset tracking, but irrelevant to multi-hop ownership attribution, regulatory standing, or fraud detection.

### Option C: International Sanctions & Beneficial Ownership Intelligence (`SELECTED`)
- *Scope:* Consolidated sanctions registries (US OFAC SDN, UK OFSI, EU Financial Sanctions, UN Security Council), Politically Exposed Persons (PEPs), Interpol Red Notices, and cross-border leaks (ICIJ Offshore Leaks: Panama Papers, Pandora Papers, Paradise Papers).
- *Marginal Value:* **EXTREMELY HIGH.** Directly closes the offshore entity opacity and regulatory sanctions blind spot identified in Eval V2.

---

## 3. Candidate Open-Source Implementations Evaluated

| Candidate Implementation | Primary Capability Claim | Upstream Source / Organization | License | License Compatibility | Operational Viability |
| :--- | :--- | :--- | :--- | :---: | :---: |
| **OpenSanctions / yente** (`v1.0.0`) | Global Sanctions, PEPs & Entity Disclosures | OpenSanctions Tech gGmbH | **Apache 2.0 / MIT** | **APPROVED** | High (Structured entity schemas, multi-jurisdiction alias matching) |
| **ICIJ Offshore Leaks Database** | Cross-border offshore trusts, shells & intermediaries | International Consortium of Investigative Journalists | **ODbL 1.0 / CC-BY-SA 4.0** | **APPROVED_WITH_ATTRIBUTION** | High (BVI, Cayman, Panama shell ownership networks) |
| **OpenOwnership Register** | Beneficial Ownership Data Standard (BODS) | OpenOwnership Global Registry | **CC0 / Public Domain** | **APPROVED** | Moderate (Covers select jurisdictions: GB, UA, SK, NG) |

---

## 4. Capability Mapping & Competition Design

The chosen candidate for recruitment evaluation is:
**`OpenSanctionsSpecialist` (Clean-room implementation leveraging the OpenSanctions entity model and Apache 2.0 `yente` reconciliation engine standard).**

### Capability Mapping:
1. **New Capability:** `sanctions_and_beneficial_ownership`
   - Declared evidence types: `OFAC_SDN_ENTRY`, `UK_OFSI_ENTRY`, `EU_SANCTIONS_ENTRY`, `UN_SANCTIONS_ENTRY`, `PEP_DISCLOSURE`, `OFFSHORE_LEAKS_RECORD`.
2. **Competition with Incumbent:**
   - On international sanctions and shell ownership tasks, `OpenSanctionsSpecialist` competes directly against `ArgusGeneralist` (`general_web_research`).
   - The competition engine must evaluate whether the structured specialist outperforms the generalist on precision, recall, hallucination resistance, and cost.

---

## 5. Security & Isolation Considerations

1. **Subprocess & Network Isolation:** Candidate execution must run behind an adapter boundary (`OpenSanctionsAdapter`). It makes zero raw network calls or subprocess executions during verified evaluation.
2. **Authoritative State Immutability:** Candidate observations must remain untrusted `NormalizedObservation` records until verified by Heimdallr Verifier.
3. **No Prompt Injection Vectors:** All entity properties and sanction summaries are sanitized through regex whitelisting before ingestion.

---

## 6. Selection Rationale Summary

Vertical 4 is formally selected as:
```text
Capability ID:      sanctions_and_beneficial_ownership
Display Name:       International Sanctions & Beneficial Ownership Intelligence
Primary Candidate:  OpenSanctionsSpecialist (v1.0.0)
License Status:     APPROVED (Apache 2.0 / MIT)
Competition Target: Argus Generalist (on sanctions queries) & Corporate Specialist (on cross-border ownership)
```
