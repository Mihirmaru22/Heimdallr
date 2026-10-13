# Vertical 5 Cross-Specialist Report: CROSS_SPECIALIST_ONION_V1

**Benchmark Suite**: `CROSS_SPECIALIST_ONION_V1`  
**Total Investigations**: 22 Tasks (20 Multi-Specialist Chains + 2 Decoys)  
**Evaluator**: Cross-Specialist Orchestration Engine  
**Proof Artifact**: `proofs/v5_cross_specialist.json`  
**Verdict**: `100% PASS` (Zero Ordering or Invocation Failures)  

---

## 1. Executive Summary

Dark-web intelligence is rarely an isolated activity. In real investigations, an initial corporate lead (e.g., an executive name or company registration) leads to a dark-web extortion portal, which extracts a cryptocurrency wallet, which is cross-referenced with OFAC sanctions or upstream infrastructure.

The `CROSS_SPECIALIST_ONION_V1` benchmark evaluates whether Heimdallr's investigation orchestrator correctly sequences state handoffs between `onion_intelligence` and existing specialists:
- `corporate_registry_intelligence`
- `infrastructure_discovery`
- `identity_resolution`
- `sanctions_and_beneficial_ownership`

---

## 2. Investigation Chains & Execution Results

| Task ID | Chain Pattern | Investigation Workflow | Required Specialists | Executed Sequence | Status |
| :--- | :--- | :--- | :--- | :--- | :---: |
| `cross_onion_01` | **Corporate $\rightarrow$ Onion** | Delaware corporate filings $\rightarrow$ ALPHV breach portal victim list | `corporate`, `onion` | `corporate` $\rightarrow$ `onion` | **PASS** |
| `cross_onion_02` | **Corporate $\rightarrow$ Onion** | UK Companies House directors $\rightarrow$ LockBit telemetry archive | `corporate`, `onion` | `corporate` $\rightarrow$ `onion` | **PASS** |
| `cross_onion_03` | **Onion $\rightarrow$ Corporate** | Onion shipping manifests $\rightarrow$ Dubai DED corporate registry | `onion`, `corporate` | `onion` $\rightarrow$ `corporate` | **PASS** |
| `cross_onion_04` | **Onion $\rightarrow$ Corporate** | Darknet leak cache $\rightarrow$ Paris Tribunal de Commerce registry | `onion`, `corporate` | `onion` $\rightarrow$ `corporate` | **PASS** |
| `cross_onion_05` | **Identity $\rightarrow$ Onion** | GitHub commit persona $\rightarrow$ Dread administrator PGP key | `identity`, `onion` | `identity` $\rightarrow$ `onion` | **PASS** |
| `cross_onion_06` | **Identity $\rightarrow$ Onion** | Author PGP identity $\rightarrow$ Darknet escrow deposit handler | `identity`, `onion` | `identity` $\rightarrow$ `onion` | **PASS** |
| `cross_onion_07` | **Onion $\rightarrow$ Identity** | ALPHV negotiation Tox ID $\rightarrow$ Clearnet developer footprint | `onion`, `identity` | `onion` $\rightarrow$ `identity` | **PASS** |
| `cross_onion_08` | **Onion $\rightarrow$ Identity** | Darknet vendor PGP signature $\rightarrow$ Academic pre-print papers | `onion`, `identity` | `onion` $\rightarrow$ `identity` | **PASS** |
| `cross_onion_09` | **Infra $\rightarrow$ Onion** | Clearnet CT log SAN entry $\rightarrow$ Backend Tor hidden service | `infrastructure`, `onion` | `infrastructure` $\rightarrow$ `onion` | **PASS** |
| `cross_onion_10` | **Infra $\rightarrow$ Onion** | BGP AS12389 announcements $\rightarrow$ Sandworm C2 Tor entry relays | `infrastructure`, `onion` | `infrastructure` $\rightarrow$ `onion` | **PASS** |
| `cross_onion_11` | **Onion $\rightarrow$ Infra** | Onion C2 egress callbacks $\rightarrow$ Public DNS nameserver query | `onion`, `infrastructure` | `onion` $\rightarrow$ `infrastructure` | **PASS** |
| `cross_onion_12` | **Onion $\rightarrow$ Infra** | LockBit fallback domains $\rightarrow$ Anycast CDN routing topology | `onion`, `infrastructure` | `onion` $\rightarrow$ `infrastructure` | **PASS** |
| `cross_onion_13` | **Sanctions $\rightarrow$ Onion** | OFAC SDN crypto addresses $\rightarrow$ Active LockBit onion publication | `sanctions`, `onion` | `sanctions` $\rightarrow$ `onion` | **PASS** |
| `cross_onion_14` | **Sanctions $\rightarrow$ Onion** | EU maritime sanctions list $\rightarrow$ Altai shadow crude oil manifests | `sanctions`, `onion` | `sanctions` $\rightarrow$ `onion` | **PASS** |
| `cross_onion_15` | **Onion $\rightarrow$ Sanctions** | Extortion crypto addresses $\rightarrow$ OFAC SDN cyber sanctions schedule | `onion`, `sanctions` | `onion` $\rightarrow$ `sanctions` | **PASS** |
| `cross_onion_16` | **Onion $\rightarrow$ Sanctions** | Andiel Escrow Ethereum wallet $\rightarrow$ UN Security Council asset freeze | `onion`, `sanctions` | `onion` $\rightarrow$ `sanctions` | **PASS** |
| `cross_onion_17` | **Corp $\rightarrow$ Identity $\rightarrow$ Onion** | UK corporate director $\rightarrow$ GitHub handle $\rightarrow$ Dread forum persona | `corporate`, `identity`, `onion` | `corporate` $\rightarrow$ `identity` $\rightarrow$ `onion` | **PASS** |
| `cross_onion_18` | **Onion $\rightarrow$ Corp $\rightarrow$ Sanctions** | Onion oil manifest $\rightarrow$ Dubai registry $\rightarrow$ US secondary sanctions | `onion`, `corporate`, `sanctions` | `onion` $\rightarrow$ `corporate` $\rightarrow$ `sanctions` | **PASS** |
| `cross_onion_19` | **Onion $\rightarrow$ Identity $\rightarrow$ Infra** | Extortion handle $\rightarrow$ GitHub developer $\rightarrow$ DNS nameserver assets | `onion`, `identity`, `infrastructure` | `onion` $\rightarrow$ `identity` $\rightarrow$ `infrastructure` | **PASS** |
| `cross_onion_20` | **4-Hop Master Chain** | Corporate registration $\rightarrow$ Mailhost DNS $\rightarrow$ ALPHV breach $\rightarrow$ Operator handle | `corporate`, `infrastructure`, `onion`, `identity` | `corporate` $\rightarrow$ `infra` $\rightarrow$ `onion` $\rightarrow$ `identity` | **PASS** |
| `cross_decoy_01` | **Decoy (Onion Bypassed)** | Clearnet beneficial ownership and OFAC SDN screening | `corporate`, `sanctions` (Onion Forbidden) | `corporate` $\rightarrow$ `sanctions` | **PASS** |
| `cross_decoy_02` | **Decoy (Onion Bypassed)** | Clearnet DNS MX verification and postmaster persona lookup | `infrastructure`, `identity` (Onion Forbidden) | `infrastructure` $\rightarrow$ `identity` | **PASS** |

---

## 3. Cross-Specialist Performance Metrics

- **Total Cross-Specialist Investigations**: 22 / 22 Passed (**100.00%**)
- **Handoff Ordering Accuracy**: **100.00%** (22 / 22)
- **Correct Specialist Invocation Rate**: **100.00%**
- **Missed Specialist Invocation Rate**: **0.00%**
- **Unnecessary Specialist Invocation Rate**: **0.00%**
- **Decoy Rejection Accuracy**: **100.00%** (2 / 2 - Onion specialist strictly excluded when irrelevant)
- **State Handoff & Provenance Integrity**: **100.00%** (evidence anchors passed cleanly without state mutation)
- **Authoritative Isolation Maintained**: **100.00%** (observations remained non-authoritative until Verifier step)
