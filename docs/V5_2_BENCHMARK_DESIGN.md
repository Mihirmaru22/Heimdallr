# HEIMDALLR V5.2 — BENCHMARK DESIGN SPECIFICATION
**Suite Name:** `ONION_CAPABILITY_GAP_V2`  
**Author:** Benchmark Auditor & Principal Research Engineer  
**Date:** 2026-10-09  
**Total Tasks:** Exactly 100 Frozen Tasks  
**Corpus:** Controlled Mock Overlay Corpus (`src/argus/evals/onion_capability_gap_v2/corpus.py`)

---

## 1. Benchmark Objectives

Previous iterations (V5.0 and V5.1) used composite benchmarks that combined search, HTTP retrieval, HTML parsing, entity extraction, and multi-hop reasoning into a single score. This introduced two critical methodological flaws:
1. **Conflation of Transport Failure with Reasoning Deficit:** When Argus failed to fetch a `.onion` page, it scored 0, falsely suggesting that Argus could not extract entities or reason over darknet intelligence.
2. **Artificial Specialist Superiority:** The standalone candidate was credited with "intelligence" simply because it retrieved documents over Tor, masking its total inability to perform cross-domain investigation.

The `ONION_CAPABILITY_GAP_V2` benchmark was constructed to decouple network transport from intelligence reasoning through six rigorous, independently graded test groups.

---

## 2. Task Group Structure (100 Tasks Total)

```
+--------------------------------------------------------------------------+
| GROUP A: Source Discovery (20 Tasks)                                    |
| Permitted index queries, decoy filtering, duplicate resolution, seeds    |
+--------------------------------------------------------------------------+
| GROUP B: Source Acquisition (20 Tasks)                                   |
| Tor transport, 301 redirects, 503 retries, timeouts, encoding, big data  |
+--------------------------------------------------------------------------+
| GROUP C: Crawling & Relevant Expansion (15 Tasks)                        |
| Link traversal, cycle detection (A->B->A), depth limits, deduplication   |
+--------------------------------------------------------------------------+
| GROUP D: Handed-Document Reasoning (15 Tasks)                            |
| Pre-acquired normalized documents: entity, temporal, contradiction tests |
+--------------------------------------------------------------------------+
| GROUP E: End-to-End Investigation (15 Tasks)                             |
| Cross-specialist multi-hop linking: Onion + Corporate + Sanctions + Infra |
+--------------------------------------------------------------------------+
| GROUP F: Negative, Budget & Epistemic Cases (15 Tasks)                   |
| Inaccessible services, budget exhaustion, NOT_FOUND / UNVERIFIED grading |
+--------------------------------------------------------------------------+
```

### Group A — Source Discovery (20 Tasks: `gap_v2_disc_001` to `gap_v2_disc_020`)
- **Objective:** Evaluate whether the system can discover valid onion hidden services from queries, seed catalogs, and decoy sets without querying live unpermitted networks.
- **Coverage:**
  - Relevant source isolated among decoy mirrors (`gap_v2_disc_001`, `006`, `010`).
  - Multiple relevant federated mirrors (`gap_v2_disc_002`, `007`).
  - Misleading page titles designed to deceive keyword matching (`gap_v2_disc_003`, `014`).
  - Queries with no valid source in permitted darknet index (`gap_v2_disc_004`, `012`, `020`).
  - Deduplication across duplicate onion mirrors (`gap_v2_disc_005`, `018`).
  - Multi-hop link expansion seeds (`gap_v2_disc_008`, `016`).

### Group B — Source Acquisition (20 Tasks: `gap_v2_acq_001` to `gap_v2_acq_020`)
- **Objective:** Evaluate Tor SOCKS5 transport retrieval robustness across realistic network conditions.
- **Coverage:**
  - Standard accessible HTML documents (`gap_v2_acq_001`, `009`, `017`).
  - HTTP 301/302 redirects to canonical onion mirrors (`gap_v2_acq_002`, `010`).
  - HTTP 503 Service Unavailable requiring bounded exponential retry (`gap_v2_acq_003`, `011`).
  - HTTP 404 / 500 permanent failures requiring clean error reporting (`gap_v2_acq_004`, `012`).
  - Large document streaming (>5MB database dumps) without OOM (`gap_v2_acq_005`, `013`).
  - Malformed and unclosed HTML tag resilience (`gap_v2_acq_006`, `014`).
  - Non-UTF8 legacy encodings (Windows-1251 Cyrillic) (`gap_v2_acq_007`, `015`).
  - Circuit timeout handling without hanging the investigation engine (`gap_v2_acq_008`, `016`).

### Group C — Crawling & Relevant Expansion (15 Tasks: `gap_v2_crawl_001` to `gap_v2_crawl_015`)
- **Objective:** Evaluate autonomous link traversal, budget enforcement, and provenance tracking.
- **Coverage:**
  - Relevant internal link prioritization (`gap_v2_crawl_001`, `007`, `011`).
  - Irrelevant link pruning (`gap_v2_crawl_002`, `008`).
  - Infinite cycle detection: Page A linking to Page B linking back to Page A (`gap_v2_crawl_003`, `012`).
  - Strict max-depth enforcement (`max_depth=2`, `max_depth=3`) (`gap_v2_crawl_004`, `009`, `013`).
  - Page budget limits (stopping cleanly at `max_pages=5`) (`gap_v2_crawl_005`, `010`, `014`).
  - Multi-path convergence deduplication (`gap_v2_crawl_006`, `015`).

### Group D — Handed-Document Reasoning (15 Tasks: `gap_v2_reas_001` to `gap_v2_reas_015`)
- **Objective:** The critical control group. All systems receive the identical pre-acquired, normalized document. This tests pure downstream reasoning without any network transport dependencies.
- **Coverage:**
  - High-precision entity extraction (Monero/BTC addresses, handles, emails) (`gap_v2_reas_001`, `006`, `011`).
  - Multi-field structured relationship parsing (`gap_v2_reas_002`, `007`, `012`).
  - Contradiction detection across syndicated mirror posts (`gap_v2_reas_003`, `008`, `013`).
  - Temporal event sequencing and timeline reconstruction (`gap_v2_reas_004`, `009`, `014`).
  - Uncorroborated darknet rumors flagged as ungrounded (`gap_v2_reas_005`, `010`, `015`).

### Group E — End-to-End Cross-Specialist Investigation (15 Tasks: `gap_v2_inv_001` to `gap_v2_inv_015`)
- **Objective:** Test end-to-end multi-specialist intelligence investigations requiring darknet acquisition linked to clearnet corporate, identity, infrastructure, or sanctions intelligence.
- **Coverage:**
  - Onion threat actor -> Clearnet corporate shell company -> Beneficial owner (`gap_v2_inv_001`, `005`, `011`).
  - Ransomware leak site -> Cryptocurrency wallet -> OFAC Sanctions list (`gap_v2_inv_002`, `006`, `012`).
  - Onion hosting service -> Clearnet BGP ASN / IP infrastructure (`gap_v2_inv_003`, `007`, `013`).
  - Darknet moniker -> Clearnet developer handle -> Verified GitHub/LinkedIn identity (`gap_v2_inv_004`, `008`, `014`).
  - Complex 4-hop synthesis across all four incumbent verticals (`gap_v2_inv_009`, `010`, `015`).

### Group F — Negative, Budget & Epistemic Cases (15 Tasks: `gap_v2_neg_001` to `gap_v2_neg_015`)
- **Objective:** Verify system behavior under uncertainty, failure, and absence of evidence.
- **Coverage:**
  - Target onion service does not exist in corpus (`gap_v2_neg_001`, `006`, `011`).
  - Onion service exists but is completely offline (`gap_v2_neg_002`, `007`, `012`).
  - Content exists but provides insufficient evidence for the query (`gap_v2_neg_003`, `008`, `013`).
  - Stale archived mirror with conflicting timestamp claims (`gap_v2_neg_004`, `009`, `014`).
  - Budget exhausted before target document reached (`gap_v2_neg_005`, `010`, `015`).

---

## 3. Epistemic Status Ground Rules

In accordance with Heimdallr engineering standards, negative results are strictly categorized:
1. **`NOT_FOUND`:** Means that after exhaustive searching within the declared, permitted search scope, no adequate evidence was discovered. **It must never be interpreted as definitive proof of universal non-existence.**
2. **`UNVERIFIED`:** Evidence was acquired from an unvetted or untrusted source (e.g., an unauthenticated darknet forum claim), but lacks independent cryptographic or official corroboration.
3. **`REFUTED`:** Definitive evidence directly disproves the proposition.
4. **`VERIFIED`:** Authoritative, cross-corroborated evidence establishes the proposition.

A system receives a grade of `FAIL` if it treats `NOT_FOUND` as `REFUTED`, or if it marks an ungrounded rumor as `VERIFIED`.

---

## 4. Controlled Test Corpus Architecture

All tests run against a hermetic, in-process mock server simulating Tor network endpoints (`MockTorCorpus`):
- **Transport Realism:** Supports custom status codes (200, 301, 404, 500, 503), headers (`Location`, `Content-Type`), delayed response simulation, and stream chunking.
- **Isolated Storage:** Zero live network calls are made during evaluation, preventing external surveillance, IP leakage, and unreproducible upstream fluctuations.
- **Decoys and Camouflage:** Features decoy mirrors (`decoy_onion_999...`), Cyrillic text encoded in `windows-1251`, cyclic links (`onion_cycle_a` -> `onion_cycle_b` -> `onion_cycle_a`), and 6MB synthetic database dumps.

---

## 5. Independent Grader Architecture

The grader operates in a separate evaluation boundary:
- Grader receives **only** the task execution output (extracted entities, fields, claims, epistemic statuses, and invocation logs).
- Grader compares outputs against frozen ground-truth objects (`GapV2TaskGroundTruth`).
- Grader enforces zero tolerance for hallucinated entities or unsupported claims.
- Grader checks whether candidate output was actually consumed in the final investigation answer before awarding candidate attribution credit.
