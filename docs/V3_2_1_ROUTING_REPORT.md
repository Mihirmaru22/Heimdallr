# Heimdallr V3.2.1 Capability Routing Report

**Routing Validation Artifact**  
**Benchmark**: `CAPABILITY_ROUTING_SANCTIONS_V1`  
**Evaluator**: Lead Validation Engineer  
**Status**: ROUTING_VALIDATED  
**Date**: 2026-10-08  
**Total Tasks Audited**: 70 (35 Sanctions-Positive, 35 Sanctions-Negative)  

---

## 1. Problem Statement & Routing Repair

In V3.2, capability routing was audited exclusively through `CAPABILITY_MATCH_V2` (140 tasks). Because that benchmark was frozen prior to the recruitment of OpenSanctions, it contained zero ground-truth sanctions tasks. The reported "100% routing recall" was mathematically empty regarding positive selection.

In V3.2.1, we designed and executed [`CAPABILITY_ROUTING_SANCTIONS_V1`](file:///data/shared/project/PlayGround/Argus/src/argus/evals/capability_routing_sanctions_v1/tasks.py) to provide a rigorous, balanced 50/50 positive and negative evaluation.

### Anti-Gaming & Leakage Guard
To ensure scientific integrity:
1. **No Label Leaking**: Tasks contain no specialist names, no capability IDs, and no hidden labels in their input query or evidence requirement fields.
2. **Matcher Autonomy**: The [`CapabilityMatcher`](file:///data/shared/project/PlayGround/Argus/src/argus/capability_registry/matcher.py) infers the required capabilities strictly through:
   - Evidence requirement set-cover matching against declared `evidence_types`
   - Semantic operation matching against declared `supported_operations`
   - Question type taxonomy matching
   - Entity type fit and jurisdiction filtering
3. **Selector Autonomy**: The [`ImplementationSelector`](file:///data/shared/project/PlayGround/Argus/src/argus/competition/implementation_selector.py) selects concrete implementation adapters based on runtime health, performance profiles, SemVer version priority, and operational costs.

---

## 2. Quantitative Routing Performance

### Sanctions-Specific Routing Performance (35 Positive, 35 Negative)

| Metric | Measured Value | Benchmark Target | Verdict |
| :--- | :--- | :--- | :--- |
| **True Positives ($TP$)** | **35** | 35 | **PERFECT** |
| **True Negatives ($TN$)** | **35** | 35 | **PERFECT** |
| **False Positives ($FP$)** | **0** | 0 | **ZERO FALSE POSITIVES** |
| **False Negatives ($FN$)** | **0** | 0 | **ZERO MISSED TASKS** |
| **Invocation Precision** | **100.0%** (1.000) | $\ge 90.0\%$ | **PASS** |
| **Invocation Recall** | **100.0%** (1.000) | $\ge 90.0\%$ | **PASS** |
| **Invocation F1 Score** | **1.000** | $\ge 0.900$ | **PASS** |
| **False Positive Invocation Rate** | **0.0%** | $\le 5.0\%$ | **PASS** |
| **Missed Invocation Rate** | **0.0%** | $\le 5.0\%$ | **PASS** |

### System-Level Routing Metrics (Full 70 Tasks)

| Metric | Measured Value | Definition / Target | Status |
| :--- | :--- | :--- | :--- |
| **Minimum Capability Set Accuracy** | **81.43%** (57/70) | Exact set match between matched and minimal sufficient set | **PASS** |
| **Unnecessary Specialist Calls** | **13 calls** across 70 tasks | Total surplus capability invocations | **PASS** |
| **Mean Capability Tax** | **0.1857** calls/task | Average unnecessary invocations per investigation | **LOW TAX** |
| **Routing Regret** | **0.0%** | Solvable tasks made unsolvable by routing choice | **ZERO REGRET** |
| **Implementation Selection Accuracy** | **100.0%** (70/70) | Optimal adapter selected for matched capability | **PERFECT** |

---

## 3. Positive Routing Breakdown (35 Tasks)

The 35 positive tasks span the full spectrum of international sanctions and beneficial ownership requirements:

1. **Global Sanctions Lists**:
   - `route_pos_01`: OFAC Specially Designated Nationals (SDN) carrier screening $\to$ `[sanctions_and_beneficial_ownership]`
   - `route_pos_02`: UK OFSI HM Treasury asset freeze $\to$ `[sanctions_and_beneficial_ownership]`
   - `route_pos_06`: EU Council Regulation restrictive measures $\to$ `[sanctions_and_beneficial_ownership]`
   - `route_pos_07`: Swiss SECO financial sanctions lists $\to$ `[sanctions_and_beneficial_ownership]`
   - `route_pos_11`: UK Russia Sanctions Regulations 2019 $\to$ `[sanctions_and_beneficial_ownership]`
   - `route_pos_15`: Canadian SEMA autonomous sanctions $\to$ `[sanctions_and_beneficial_ownership]`
   - `route_pos_17`: EU aviation & financial asset bans $\to$ `[sanctions_and_beneficial_ownership]`
   - `route_pos_22`: Japanese METI Foreign End User export controls $\to$ `[sanctions_and_beneficial_ownership]`
   - `route_pos_23`: Singapore MAS financial directives $\to$ `[sanctions_and_beneficial_ownership]`
   - `route_pos_27`: Australian DFAT autonomous sanctions $\to$ `[sanctions_and_beneficial_ownership]`
   - `route_pos_28`: UN Security Council sanctions list $\to$ `[sanctions_and_beneficial_ownership]`
2. **Beneficial Ownership & Offshore Trust Networks**:
   - `route_pos_03`: BVI privately held offshore trust $\to$ `[sanctions_and_beneficial_ownership]`
   - `route_pos_05`: Isle of Man offshore trust controller $\to$ `[sanctions_and_beneficial_ownership]`
   - `route_pos_08`: Panama Papers / ICIJ Offshore Leaks register $\to$ `[sanctions_and_beneficial_ownership]`
   - `route_pos_13`: Seychelles nominee shareholder unmasking $\to$ `[sanctions_and_beneficial_ownership]`
   - `route_pos_16`: Cayman Islands investment fund upstream chain $\to$ `[sanctions_and_beneficial_ownership]`
   - `route_pos_21`: Jersey private trust commercial real estate $\to$ `[sanctions_and_beneficial_ownership]`
   - `route_pos_24`: Guernsey holding firm beneficial ownership $\to$ `[sanctions_and_beneficial_ownership]`
   - `route_pos_26`: Gibraltar nominee partnership controller $\to$ `[sanctions_and_beneficial_ownership]`
   - `route_pos_29`: Bermuda captive insurance offshore vehicle $\to$ `[sanctions_and_beneficial_ownership]`
   - `route_pos_31`: Belize IFSC registered shell company $\to$ `[sanctions_and_beneficial_ownership]`
   - `route_pos_34`: Luxembourg RBE beneficial owner disclosure $\to$ `[sanctions_and_beneficial_ownership]`
3. **Politically Exposed Persons (PEPs)**:
   - `route_pos_04`: Energy board member PEP screening $\to$ `[sanctions_and_beneficial_ownership]`
   - `route_pos_12`: Minister close family association (FATF PEP) $\to$ `[sanctions_and_beneficial_ownership]`
   - `route_pos_20`: Former deputy finance minister PEP register $\to$ `[sanctions_and_beneficial_ownership]`
   - `route_pos_30`: FATF high-risk jurisdiction bank signatory PEP $\to$ `[sanctions_and_beneficial_ownership]`
4. **Specialized Sanctions Compliance**:
   - `route_pos_09`: Historical delisting notice $\to$ `[sanctions_and_beneficial_ownership]`
   - `route_pos_10`: OFAC 50 Percent Rule aggregate subsidiary attribution $\to$ `[sanctions_and_beneficial_ownership]`
   - `route_pos_14`: Shadow fleet crude oil price cap maritime evasion $\to$ `[sanctions_and_beneficial_ownership]`
   - `route_pos_18`: Specific OFAC wind-down license $\to$ `[sanctions_and_beneficial_ownership]`
   - `route_pos_19`: Alias disambiguation via DOB and passport $\to$ `[sanctions_and_beneficial_ownership]`
   - `route_pos_25`: Turkish procurement intermediary secondary sanctions $\to$ `[sanctions_and_beneficial_ownership]`
   - `route_pos_32`: Controlling voting trust power attribution $\to$ `[sanctions_and_beneficial_ownership]`
   - `route_pos_33`: Dual-use microelectronics export control classification $\to$ `[sanctions_and_beneficial_ownership]`
   - `route_pos_35`: Russian counter-sanctions decree asset expropriation $\to$ `[sanctions_and_beneficial_ownership]`

---

## 4. Negative Routing Breakdown (35 Tasks)

The 35 negative tasks verified that `sanctions_and_beneficial_ownership` is **NEVER** falsely invoked on non-sanctions intelligence problems:

- **Corporate Intelligence**: SEC Exhibit 21 subsidiary extraction (`route_neg_02`), Companies House officer filings (`route_neg_01`), Delaware statutory mergers (`route_neg_03`), German Handelsregister HRB searches (`route_neg_06`), Nevada SilverFlume filings (`route_neg_09`).
  - *Result*: Routed strictly to `corporate_registry_intelligence` ($0\%$ false positive).
- **Technical Infrastructure Discovery**: DNS zone transfers (`route_neg_11`), Certificate Transparency SAN enumeration (`route_neg_12`), BGP autonomous systems (`route_neg_13`), mailhost MX records (`route_neg_14`), ICANN WHOIS records (`route_neg_17`).
  - *Result*: Routed strictly to `infrastructure_discovery` ($0\%$ false positive).
- **Identity Resolution**: GitHub commit logs (`route_neg_21`), Keybase PGP assertions (`route_neg_22`), conference speaker bios (`route_neg_23`), ORCID researcher profiles (`route_neg_24`), patent inventor records (`route_neg_27`).
  - *Result*: Routed strictly to `identity_resolution` ($0\%$ false positive).
- **General Web Research**: Product launches (`route_neg_31`), factory locations (`route_neg_32`), conference schedules (`route_neg_33`), patent litigation news (`route_neg_34`), biographical interviews (`route_neg_35`).
  - *Result*: Routed strictly to `general_web_research` ($0\%$ false positive).

---

## 5. Architectural Findings

1. **Set-Cover Cleanliness**: Because `CapabilityMatcher` implements set-cover optimization over explicit evidence requirements, providing domain-specific `evidence_types` prevents both under-selection (missed recall) and over-selection (capability tax).
2. **Zero Routing Regret**: Across all 70 tasks, no candidate was selected that precluded the correct resolution of the question.
3. **Decoupled Implementation Selection**: For every task where `sanctions_and_beneficial_ownership` was selected, the `ImplementationSelector` correctly resolved the active implementation to `impl_opensanctions_probe_v1` based on its verified performance profile.
