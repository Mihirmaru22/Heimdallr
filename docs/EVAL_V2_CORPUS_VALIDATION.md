# HEIMDALLR EVAL V2 — CORPUS COVERAGE & GRAPH VALIDATION REPORT

- **Benchmark Version:** Eval V2.1 (`genuine_execution_recovery`)
- **Validation Status:** PASSED (100% EXECUTABLE)
- **Total Tasks Evaluated:** 129
- **Total Registered Corpus Documents:** 175
- **Total Discoverable Entities:** 165
- **Impossible Tasks:** 0
- **Orphaned Expected Entities:** 0
- **Missing Hop Evidence Snippets:** 0

---

## 1. Corpus Design Principles & Validation Invariants

Every document in `CORPUS_V2_REGISTRY` satisfies the strict Eval V2 anti-gaming invariants:
1. **Evaluator Truth Isolation:** Zero evaluator metadata (`task_id`, `category`, `expected_entities`, `pass/fail`) exists in document content or URLs.
2. **Multi-Domain Distribution:** Evidence spans SEC EDGAR, UK Companies House, Certificate Transparency logs, DNS zones, WHOIS, OSINT platforms (GitHub, Keybase, LinkedIn), Reuters/Bloomberg, Lancet Oncology, and academic repositories (arXiv).
3. **Multi-Hop Traversal Integrity:** Each intermediate hop node ($H_1 \to H_2 \to H_3$) is discoverable via preceding documents rather than collapsed into a single answer document.
4. **Realistic Ambiguity & Noise:** Distractor entities, lookalike phishing domains (`finbank-g1obal.com`), commercial registered agents (`Corporation Service Company`), and superseded Form 10-K filings exist alongside authoritative sources.
5. **Negative Search Noise:** All 20 negative, UNKNOWN, and research stopping tasks contain realistic market commentary and sector overviews that verify lack of public records without target hallucination.

---

## 2. Category Coverage Summary

| Category | Tasks | Backing Documents Available | Domain Sources | Validation Status |
| :--- | :---: | :---: | :--- | :---: |
| `ADVERSARIAL_ENTITY_CONFUSION` | 5 | 6 | find-and-update.company-information.service.gov.uk, www.corporate-registry-search.gov, www.sec.gov | **VERIFIED** |
| `CONTRADICTION_RESOLUTION` | 5 | 6 | www.sec.gov | **VERIFIED** |
| `CORPORATE_REGISTRY_INTELLIGENCE` | 5 | 5 | www.sec.gov | **VERIFIED** |
| `CROSS_SPECIALIST_INVESTIGATION` | 6 | 18 | crt.sh, www.linkedin.com, www.sec.gov | **VERIFIED** |
| `DEEP_ENTITY_RESOLUTION` | 5 | 9 | find-and-update.company-information.service.gov.uk, search.gleif.org | **VERIFIED** |
| `EFFICIENCY` | 5 | 5 | www.executive-registry.org | **VERIFIED** |
| `EPISTEMIC_CLASSIFICATION` | 5 | 5 | www.regulatory-disclosure.org | **VERIFIED** |
| `EVIDENCE_GROUNDING` | 5 | 9 | www.globenewswire-mirror.com, www.marketwatch-syndicated.com, www.reuters.com | **VERIFIED** |
| `GENERAL_ENTITY_DISCOVERY` | 5 | 7 | find-and-update.company-information.service.gov.uk, www.delaware-gov.us, www.sec.gov | **VERIFIED** |
| `IDENTITY_INTELLIGENCE` | 5 | 7 | find-and-update.company-information.service.gov.uk, github.com, www.linkedin.com | **VERIFIED** |
| `INFRASTRUCTURE_INTELLIGENCE` | 5 | 5 | crt.sh | **VERIFIED** |
| `LEADERSHIP_INTELLIGENCE` | 5 | 5 | www.sec.gov | **VERIFIED** |
| `LONG_HORIZON_INVESTIGATION` | 5 | 10 | www.global-conglomerates.com, www.operating-arms-directory.org | **VERIFIED** |
| `MISSING_INFORMATION_NOT_FOUND` | 5 | 0 | Market Noise | **VERIFIED** |
| `MULTI_HOP_INVESTIGATION` | 8 | 27 | crt.sh, find-and-update.company-information.service.gov.uk, www.leadership-directory.org | **VERIFIED** |
| `NEGATIVE_INTELLIGENCE` | 5 | 0 | Market Noise | **VERIFIED** |
| `REGRESSION_HISTORICAL_CAPABILITY` | 5 | 5 | www.historical-archive-registry.org | **VERIFIED** |
| `RESEARCH_STOPPING` | 5 | 0 | Market Noise | **VERIFIED** |
| `SECURITY_PROMPT_INJECTION` | 5 | 5 | www.adversarial-forum-sample.net, www.dark-security-forum.org | **VERIFIED** |
| `SOURCE_QUALITY_AUTHORITY` | 5 | 5 | www.sec.gov | **VERIFIED** |
| `SPECIALIST_NON_INVOCATION` | 5 | 5 | arxiv.org | **VERIFIED** |
| `SPECIALIST_ROUTING` | 5 | 5 | dns-lookup.zone | **VERIFIED** |
| `STRUCTURED_EXTRACTION` | 5 | 6 | find-and-update.company-information.service.gov.uk, www.sec.gov | **VERIFIED** |
| `TEMPORAL_INTELLIGENCE` | 5 | 5 | find-and-update.company-information.service.gov.uk | **VERIFIED** |
| `UNKNOWN_HANDLING` | 5 | 0 | Market Noise | **VERIFIED** |

---

## 3. Flagship Multi-Hop Investigation Validation

### Task `v2_cat08_task01_flagship_6hop`
Chain Dependency: $\text{AeroDynamics Corp} \to \text{AeroDynamics UK} \to \text{AeroSpace Orbital} \to \text{orbital-telemetry} \to \text{Dr. Viktor Kroll} \to \text{Nordic Space} \to \text{Horizon Aerospace}$

| Hop | Source Entity | Predicate | Target Entity | Evidence Snippet Grounded? | Backing Document |
| :---: | :--- | :--- | :--- | :---: | :--- |
| H1 | `AeroDynamics Corp` | `subsidiary` | `AeroDynamics UK Limited` | **YES** | `sec_edgar_aerodynamics_10k_2023` |
| H2 | `AeroDynamics UK Limited` | `subsidiary` | `AeroSpace Orbital Systems Ltd` | **YES** | `ch_aerodynamics_uk_profile` |
| H3 | `AeroSpace Orbital Systems Ltd` | `infrastructure` | `orbital-telemetry.aerospace-uk.com` | **YES** | `dns_ct_orbital_telemetry` |
| H4 | `AeroSpace Orbital Systems Ltd` | `officer` | `Dr. Viktor Kroll` | **YES** | `ch_aerospace_orbital_profile` |
| H5 | `Dr. Viktor Kroll` | `former_employer` | `Nordic Space GmbH` | **YES** | `linkedin_dr_viktor_kroll` |
| H6 | `Horizon Aerospace` | `acquired` | `Nordic Space GmbH` | **YES** | `news_nordic_space_acquisition` |

---

## 4. Verification Conclusion

All 129 benchmark tasks now have complete, authentic backing documents in `CORPUS_V2_REGISTRY`. Zero tasks contain orphaned expectations or missing evidence. The benchmark is 100% executable through genuine research traversal.
