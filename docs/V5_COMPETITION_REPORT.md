# Vertical 5 Competition Report: Candidate Evaluation & Coexistence

**Benchmark Suite**: `ONION_SPECIALIST_V1` (100 Tasks)  
**Evaluated Systems**: Argus Baseline, Ahmia Reference, TorBot Reference, Clean-Room Unified Implementation  
**Proof Artifact**: `proofs/v5_competition.json`  
**Architectural Decision**: `COEXIST`  

---

## 1. Upstream Reference Projects vs Recruited Implementation

To prevent intellectual property confusion and ensure strict license hygiene, Heimdallr formally distinguishes **Upstream / Reference Projects** from the **Recruited Implementation**:

| Project / Candidate | Classification | License | Operational Role in Heimdallr |
| :--- | :--- | :--- | :--- |
| **Ahmia** | **REFERENCE / SOURCE OF CAPABILITY INSPIRATION** | BSD-3-Clause | Conceptual model for hidden service search indexing; live server scraping prohibited; local index schemas used as reference. |
| **TorBot** | **REFERENCE / SOURCE OF CAPABILITY INSPIRATION** | GPL-3.0 (Copyleft) | Conceptual model for recursive onion crawling and regex cryptocurrency extraction. **Direct upstream code incorporation strictly rejected.** Zero lines of GPL-3.0 code imported. |
| **Heimdallr Unified Onion Engine** (`impl_onion_integrated_v1`) | **RECRUITED IMPLEMENTATION** | Apache-2.0 (Clean-Room) | Natively authored clean-room implementation providing search, crawling, and extraction within an unprivileged adapter boundary. |

---

## 2. Head-to-Head Benchmark Results

All configurations were evaluated against the identical 100-task frozen benchmark suite:

| Configuration | System Architecture | Tasks Passed | Pass Rate | Key Strengths & Failure Modes |
| :--- | :--- | :---: | :---: | :--- |
| **1. Incumbent Standalone** | Argus Generalist | 15 / 100 | **15.00%** | Passes NOT_FOUND/UNKNOWN queries; 0% recall on dark-web tasks. |
| **2a. Reference Standalone: Ahmia** | Ahmia Search Engine | 75 / 100 | **75.00%** | Solves indexed search; fails recursive crawling and crypto extraction. |
| **2b. Reference Standalone: TorBot** | TorBot Clean-Room Crawler | 75 / 100 | **75.00%** | Solves crawl & extraction; fails keyword search without seed URL. |
| **2c. Recruited Standalone: Unified**| Clean-Room Unified Engine | 95 / 100 | **95.00%** | Solves search, crawl, and extraction; fails only clearnet multi-hop. |
| **3a. Reference Integrated: Ahmia** | Heimdallr + Ahmia | 86 / 100 | **86.00%** | Solves clearnet multi-hop; fails unindexed crawling tasks. |
| **3b. Reference Integrated: TorBot** | Heimdallr + TorBot | 86 / 100 | **86.00%** | Solves clearnet multi-hop; fails search discovery tasks. |
| **4. Integrated Coexistence** | Heimdallr + Unified Clean-Room | **100 / 100** | **100.00%** | **Full benchmark completion via search + crawl + multi-specialist synthesis.** |
| **5. Candidate Disabled** | Heimdallr (Onion Disabled) | 15 / 100 | **15.00%** | Collapses back to Argus baseline. |

---

## 3. Disambiguation of Synergy Metrics

To ensure strict clarity across all reports and JSON proofs, three distinct synergy-related metrics are defined:

### Metric 1: `candidate_coexistence_synergy_wins` = 4
- **Definition**: The count of tasks where the candidate standalone failed due to domain isolation (requiring clearnet corporate or sanctions registries), but integrated coexistence succeeded through multi-specialist synthesis:
  $$\text{A (FAIL)} \longrightarrow \text{B (FAIL)} \longrightarrow \text{C (PASS)} \longrightarrow \text{D (FAIL)}$$
- **Numerator**: 4 tasks
- **Denominator**: 100 tasks
- **Task IDs**: `ONION_HOP_01`, `ONION_CRS_01`, `ONION_CRS_02`, `ONION_CRS_03`
- **Calculation**: $4 / 100 = 4.0\%$

### Metric 2: `coexistence_gain_over_ahmia` = +14
- **Definition**: The net performance improvement of Integrated Coexistence (100/100) over Ahmia Integrated alone (86/100), representing tasks requiring deep page crawling and regex crypto extraction that search engines cannot execute.
- **Numerator**: 14 tasks
- **Denominator**: 100 tasks
- **Task IDs**: `ONION_CRW_01`–`07` (Crawling), `ONION_ENT_01`–`07` (Crypto/PGP extraction)
- **Calculation**: $100 - 86 = 14$ tasks ($+14.0\%$)

### Metric 3: `coexistence_gain_over_torbot` = +14
- **Definition**: The net performance improvement of Integrated Coexistence (100/100) over TorBot Integrated alone (86/100), representing tasks requiring unindexed keyword search and descriptor discovery that crawlers cannot execute without pre-existing URLs.
- **Numerator**: 14 tasks
- **Denominator**: 100 tasks
- **Task IDs**: `ONION_DISC_01`–`07` (Service Discovery), `ONION_SRCH_01`–`07` (Keyword Search)
- **Calculation**: $100 - 86 = 14$ tasks ($+14.0\%$)

**Important**: These three metrics measure distinct operational comparisons and are never merged or conflated.

---

## 4. Implementation Selector Configuration

In Heimdallr's capability registry, `onion_intelligence` registers the unified clean-room implementation as the primary engine:

```json
{
  "capability_id": "onion_intelligence",
  "primary_implementation": "impl_onion_integrated_v1",
  "implementations": [
    {
      "implementation_id": "impl_onion_integrated_v1",
      "role": "PRIMARY_UNIFIED_ENGINE",
      "license": "Apache-2.0 (Clean-Room)",
      "f1_score": 0.980,
      "cost_per_query": 0.002
    },
    {
      "implementation_id": "impl_ahmia_search_v1",
      "role": "SPECIALIZED_SEARCH_ADAPTER",
      "license": "BSD-3-Clause",
      "f1_score": 0.820,
      "cost_per_query": 0.001
    },
    {
      "implementation_id": "impl_torbot_crawler_v1",
      "role": "SPECIALIZED_CRAWLER_ADAPTER",
      "license": "Apache-2.0 (Clean-Room)",
      "f1_score": 0.787,
      "cost_per_query": 0.0015
    }
  ]
}
```

The unified engine delivers optimal accuracy while preserving absolute license safety.
