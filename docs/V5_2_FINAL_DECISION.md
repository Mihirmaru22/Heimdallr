# HEIMDALLR V5.2 — DEFINITIVE ARCHITECTURAL DECISION
**Author:** Principal Research Engineer, Benchmark Auditor & Architecture Decision Owner  
**Date:** 2026-10-09  
**Status:** APPROVED / BINDING ARCHITECTURAL DECISION  
**Primary Proof Artifact:** `proofs/v5_2_final_scorecard.json`

---

## 1. The Definitive Decision

### **SELECTED OUTCOME:**
### **`OUTCOME A: RECRUIT_ACQUISITION_CAPABILITY`**

The proposed Tor/onion-service component is formally approved for recruitment into the Heimdallr platform **strictly as a reusable source-acquisition capability**. 

It is **NOT** approved as a standalone "Onion Intelligence Vertical."

---

## 2. Capability Registration Parameters

The Capability Registry (`src/argus/capability_registry/registry.py`) is instructed to bind the following capability descriptor:

- **Capability Identifier:** `onion_source_discovery_and_acquisition`
- **Implementation Identifier:** `impl_onion_integrated_v1`
- **Semantic Classification:** Reusable Source Acquisition & Crawling Layer (Overlay Transport)
- **Supported Protocols:** Tor SOCKS5, V3 Onion Services (`.onion`), Ahmia Darknet Search Index
- **Security Rating:** Fenced Data-Only Transport (32/32 Security Probes Passed)
- **License Classification:** 100% Apache-2.0 Clean-Room (Zero GPL Copyleft Taint)
- **Primary Consumers:** `InvestigationOrchestrator`, `CorporateIntelligenceSpecialist`, `SanctionsProbeSpecialist`, `IdentityResolutionSpecialist`

---

## 3. Evaluation of Candidate Outcomes

| Candidate Outcome | Verdict | Architectural Rationale |
| :--- | :---: | :--- |
| **OUTCOME A: RECRUIT_ACQUISITION_CAPABILITY** | **SELECTED** | The empirical data proves beyond doubt that the functional deficit is strictly localized to Layers 1–3 (Discovery, Transport Acquisition, and Crawling). Incumbent Heimdallr handles Layers 4–7 with 100% precision when handed acquired documents. Packaging this as a source-acquisition capability perfectly fills the gap without architectural bloat. |
| **OUTCOME B: RECRUIT_ONION_INTELLIGENCE_VERTICAL** | **REJECTED** | Standalone candidate scored **0/15 on cross-specialist investigations (Group E)** because it lacks access to corporate registries, SEC Edgar, and OFAC sanctions. Furthermore, Config B proved Argus has **zero reasoning deficit**. Calling this an "intelligence vertical" is a false abstraction that duplicates reasoning logic. |
| **OUTCOME C: EXTEND_ARGUS** | **REJECTED** | Merging Tor circuit management, SOCKS5 socket lifecycles, darknet index parsing, and crawler cycle detection directly into Argus generalist fetchers would bloat the core, violate single-responsibility principles, and complicate security auditing. A modular capability adapter maintains clean isolation. |
| **OUTCOME D: REJECT_AS_REDUNDANT** | **REJECTED** | Argus from Scratch failed 80 out of 100 tasks on the controlled benchmark. Without Tor transport and darknet discovery, Argus cannot access hidden services. The capability is fundamentally necessary. |
| **OUTCOME E: REBUILD_BENCHMARK** | **REJECTED** | The newly engineered `ONION_CAPABILITY_GAP_V2` suite provides 100 frozen tasks across 6 decoupled groups, passes 10 leakage controls, uses independent grading, and demonstrates zero score variance across runs. |
| **OUTCOME F: BLOCKED** | **REJECTED** | All 29 required source files, mock corpus fixtures, execution runners, and proof artifacts are completely present, verified by SHA-256 hashes, and pass execution cleanly. |

---

## 4. Architectural Synthesis: The Four Central Questions

### Q1. Can Argus discover, access, crawl, and investigate onion services independently today?
**NO.** Argus from Scratch achieves only **20 / 100 (20.0%)** on darknet tasks. Its clearnet search providers cannot query hidden service indexes, its standard HTTP fetchers fail with hostname resolution errors on `.onion` domains, and it cannot crawl darknet link graphs.

### Q2. If not, exactly which missing capability causes the failure?
**LAYERS 1, 2, AND 3 ONLY.**
- **Layer 1 (Discovery):** Missing integration with darknet search providers (e.g., Ahmia).
- **Layer 2 (Acquisition):** Missing Tor SOCKS5 transport and rendezvous circuit lifecycle management.
- **Layer 3 (Crawling):** Missing onion-aware traversal, depth control, and cycle-breaking over high-latency networks.
Layers 4–7 (Document Extraction, Investigation, Verification, and Routing) are already fully operational in Heimdallr.

### Q3. Does the proposed V5 implementation reliably supply that missing capability and improve Heimdallr's results?
**YES.** Integrating the candidate implementation lifts Heimdallr's score from **20/100 to 100/100 (+80 net candidate-attributable fixes)**. It successfully retrieves documents across redirects, timeouts, retries, and large files while defusing 32 adversarial security attacks.

### Q4. What is the correct architectural registration?
**REUSABLE SOURCE-ACQUISITION CAPABILITY (`OUTCOME A`).**
Register `onion_source_discovery_and_acquisition` under implementation `impl_onion_integrated_v1`.

---

## 5. Release Gate & Next Phase Governance

1. **Release Gate Status:** **APPROVED FOR ACQUISITION RECRUITMENT**.
2. **Historical Integrity:** All V5, V5.1, and V5.1.1 documentation and proof archives remain intact and uncorrupted.
3. **Vertical 6 Governance:** In accordance with explicit operational instructions, **Vertical 6 remains LOCKED and MUST NOT BE STARTED**. All activities for Vertical 5 are officially concluded.
