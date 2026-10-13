# HEIMDALLR V5.2 — CAPABILITY BOUNDARY SPECIFICATION
**Author:** Principal Research Engineer, Benchmark Auditor & Architecture Decision Owner  
**Date:** 2026-10-09  
**Status:** DEFINITIVE / ARCHITECTURAL BASELINE  
**Artifact Hash:** Derived from Git Commit `56c62b5008219f558c89a79c34cd1bf5ec0f4d79`

---

## 1. Executive Statement

The central architectural confusion in Vertical 5 was conflating **source discovery and acquisition over an overlay network** with a **novel intelligence reasoning vertical**. 

An intelligence vertical (such as Corporate Intelligence or Sanctions Intelligence) introduces unique domain semantics, ontology models, specialized regulatory reasoning, and entity-resolution logic. In contrast, onion services (`.onion` hidden services) represent an **encrypted, onion-routed network transport layer**. 

This document defines the definitive capability boundary across seven discrete layers, analyzing existing Argus capabilities, incumbent Heimdallr capabilities, the proposed V5 candidate implementation, and the exact functional deficit.

---

## 2. Seven-Layer Capability Boundary Analysis

```
+-------------------------------------------------------------------------+
| Layer 7: Specialist Orchestration (Matcher / Capability Registry / Router) |
+-------------------------------------------------------------------------+
| Layer 6: Verification & Epistemic Status (Contradictions / Grounding)     |
+-------------------------------------------------------------------------+
| Layer 5: End-to-End Investigation (Hypothesis Generation / Multi-Hop)   |
+-------------------------------------------------------------------------+
| Layer 4: Document Intelligence (Field Extraction / Entity Resolution)   |
+-------------------------------------------------------------------------+
| Layer 3: Crawling & Traversal (Link Expansion / Depth / Cycle Control)  | <--- DEFICIT
+-------------------------------------------------------------------------+
| Layer 2: Acquisition & Transport (Tor SOCKS5 / Circuit Isolation / Retries)| <--- DEFICIT
+-------------------------------------------------------------------------+
| Layer 1: Source Discovery (Ahmia Index / Seed Resolution / Decoys)      | <--- DEFICIT
+-------------------------------------------------------------------------+
```

### Layer 1 — Source Discovery
*Can the system identify relevant onion services from permitted indexes, known links, and supplied seed information?*
- **Existing Argus Implementation:** Clearnet search providers (`DuckDuckGoSearchProvider`, `GoogleSearchProvider`, `HybridSearchProvider`). These engines do not index `.onion` hidden services and cannot query darknet indexers.
- **Existing Heimdallr Implementation:** Relies exclusively on Argus clearnet search providers.
- **Proposed V5 Implementation:** Ahmia search adapter (`impl_ahmia_search_v1`) accessing permitted hidden-service search indexes and seed registries.
- **Deficit / Gap:** **CRITICAL GAP**. Argus cannot discover `.onion` addresses from darknet search engines; clearnet search returns zero results for internal onion content.
- **Supporting Evidence:** Argus from Scratch (Config A) failed 18 out of 20 discovery tasks (Precision: 0.10, Recall: 0.10).
- **Benchmark Evaluation:** `ONION_CAPABILITY_GAP_V2` Group A (20 tasks).

---

### Layer 2 — Source Acquisition & Transport
*Can the system connect through an appropriately configured Tor transport and retrieve permitted onion-service content?*
- **Existing Argus Implementation:** `TwoTierFetcher`, `PlaywrightFetcher`, `CrawleeEngine`. All clearnet fetchers resolve hostnames via standard DNS (`getaddrinfo`) and connect via standard TCP sockets. They lack SOCKS5 proxy support, `.onion` domain resolution, and circuit timeout handling.
- **Existing Heimdallr Implementation:** Same as Argus clearnet fetchers.
- **Proposed V5 Implementation:** Tor-transport fetcher (`OnionTransportClient`) routing requests through local Tor SOCKS5 proxy (`127.0.0.1:9050`), supporting rendezvous circuit timeouts, 503 retry backoff, and encoding normalizers.
- **Deficit / Gap:** **CRITICAL GAP**. Standard HTTP clients immediately throw `gaierror: [Errno -2] Name or service not known` or connection reset when attempting to resolve `.onion` domains.
- **Supporting Evidence:** Argus from Scratch (Config A) failed 17 out of 20 acquisition tasks (Success rate: 15.0%, passing only 3 negative/invalid URL cases).
- **Benchmark Evaluation:** `ONION_CAPABILITY_GAP_V2` Group B (20 tasks).

---

### Layer 3 — Crawling & URL Traversal
*Can the system follow relevant links, manage depth, deduplicate pages, and preserve source relationships over onion services?*
- **Existing Argus Implementation:** `ArgusCrawlerEngine` and `CrawleeEngine`. Capable of BFS/DFS crawling on clearnet domains, but cannot crawl `.onion` domains due to Layer 2 transport failure.
- **Existing Heimdallr Implementation:** Same as Argus.
- **Proposed V5 Implementation:** Clean-room crawler engine (`impl_torbot_crawler_v1`) implementing bounded-depth traversal, SHA-256 page deduplication, cycle detection (preventing `A -> B -> A` loops), and provenance tree preservation.
- **Deficit / Gap:** **CRITICAL GAP**. While crawling algorithms are generic, traversal over high-latency onion services requires specialized rate-limiting, circuit reuse, and cycle detection tailored to Tor latency characteristics.
- **Supporting Evidence:** Argus from Scratch (Config A) scored 0/15 on onion crawling tasks. Standalone candidate scored 15/15.
- **Benchmark Evaluation:** `ONION_CAPABILITY_GAP_V2` Group C (15 tasks).

---

### Layer 4 — Document Intelligence & Extraction
*Can the system extract structured content, entities, and relationships while preserving provenance?*
- **Existing Argus Implementation:** `DocumentExtractor`, regex entity parsers, markdown converters, table extractors.
- **Existing Heimdallr Implementation:** Comprehensive entity resolution (`impl_identity_probe_specialist_v1`), structured schema validation, PII masking.
- **Proposed V5 Implementation:** HTML parser extracting text, metadata, PGP fingerprints, cryptocurrency addresses, and links.
- **Deficit / Gap:** **NO DEFICIT IN REASONING**. Once raw HTML/text is acquired, Argus and Heimdallr incumbent extractors parse `.onion` documents identically to clearnet documents.
- **Supporting Evidence:** In Group D (Handed-Document Reasoning), Argus with handed documents (Config B) scored **15/15 (100%)**, matching Heimdallr Integrated (15/15) and outperforming standalone onion specialist (12/15).
- **Benchmark Evaluation:** `ONION_CAPABILITY_GAP_V2` Group D (15 tasks).

---

### Layer 5 — Investigation & Lead Following
*Can the system formulate hypotheses, follow multi-hop leads across jurisdictions, and coordinate multi-source research?*
- **Existing Argus Implementation:** Basic single-tier search and scrapers.
- **Existing Heimdallr Implementation:** `InvestigationOrchestrator`, multi-hop lead generation, cross-specialist graph expansion (linking corporate records, sanctions, infrastructure, and identities).
- **Proposed V5 Implementation:** Standalone specialist only performs keyword extraction; it has zero access to corporate registries, SEC EDGAR, or sanctions databases.
- **Deficit / Gap:** **NO DEFICIT IN HEIMDALLR; FATAL DEFICIT IN STANDALONE SPECIALIST**. Standalone candidate scored **0/15** on cross-specialist investigations (Group E) because it cannot resolve clearnet corporate entities or OFAC sanctions.
- **Supporting Evidence:** Config C scored 0/15 on Group E; Config D (Heimdallr integrated with onion acquisition) scored 15/15.
- **Benchmark Evaluation:** `ONION_CAPABILITY_GAP_V2` Group E (15 tasks).

---

### Layer 6 — Verification & Epistemic Status
*Can the system verify claims, handle contradictions, assign correct epistemic statuses, and respect search scope limits?*
- **Existing Argus Implementation:** Epistemic classifier (`VERIFIED`, `REFUTED`, `UNVERIFIED`, `NOT_FOUND`).
- **Existing Heimdallr Implementation:** Strict evidence provenance verification, contradiction detection engines, authoritative fencing.
- **Proposed V5 Implementation:** Basic status flags on extracted items.
- **Deficit / Gap:** **NO DEFICIT IN HEIMDALLR**. Heimdallr's existing verification engine correctly flags uncorroborated darknet rumors as `UNVERIFIED` and bounded search scope misses as `NOT_FOUND`.
- **Supporting Evidence:** In Group F (Negative & Epistemic Cases), both Argus baseline and Heimdallr scored 15/15 (100%), demonstrating that epistemic caution is already native to the platform.
- **Benchmark Evaluation:** `ONION_CAPABILITY_GAP_V2` Group F (15 tasks).

---

### Layer 7 — Specialist Orchestration & Routing
*Can the Capability Registry invoke the required capability only when appropriate, avoiding unnecessary darknet queries?*
- **Existing Argus Implementation:** Static provider selection.
- **Existing Heimdallr Implementation:** Dynamic capability matcher (`CapabilityMatcher`, `CapabilityRegistry`) routing based on query intent, domain indicators, and evidence requirements.
- **Proposed V5 Implementation:** Integrated adapter registering `onion_source_discovery_and_acquisition`.
- **Deficit / Gap:** **NO DEFICIT**. The incumbent registry routes `.onion` queries with 100% precision and 100% recall.
- **Supporting Evidence:** V5.2 Routing benchmark achieved 50/50 TP, 50/50 TN, 0 FP, 0 FN (Precision: 1.0, Recall: 1.0, F1: 1.0).
- **Benchmark Evaluation:** `proofs/v5_2_routing_metrics.json`.

---

## 3. Definitive Capability Boundary Matrix

| Capability Layer | Incumbent Argus / Heimdallr Status | Candidate Standalone Status | Gap Identified? | Architectural Home |
| :--- | :--- | :--- | :--- | :--- |
| **Layer 1: Discovery** | Missing (Clearnet only) | Present (Ahmia index adapter) | **YES** | Acquisition Specialist |
| **Layer 2: Acquisition** | Missing (Standard DNS/TCP) | Present (Tor SOCKS5 client) | **YES** | Acquisition Specialist |
| **Layer 3: Crawling** | Missing for .onion | Present (Clean-room crawler) | **YES** | Acquisition Specialist |
| **Layer 4: Document Intelligence** | Native & Complete | Redundant & Incomplete | **NO** | Heimdallr Incumbent |
| **Layer 5: Investigation** | Native & Complete | Absent (No clearnet registries)| **NO** | Heimdallr Incumbent |
| **Layer 6: Verification** | Native & Complete | Absent | **NO** | Heimdallr Incumbent |
| **Layer 7: Orchestration** | Native & Complete | N/A (Adapter only) | **NO** | Heimdallr Incumbent |

---

## 4. Architectural Conclusion

The empirical evidence demonstrates that **the gap is strictly localized to Layers 1, 2, and 3** (Overlay Network Discovery, Transport Acquisition, and Traversal).

There is **zero justification** for a separate "Onion Intelligence Vertical" (which would duplicate Layers 4–7). All downstream reasoning, cross-specialist entity resolution, temporal reconciliation, and epistemic verification are best handled by Heimdallr's existing engine.

Therefore, the capability must be recruited strictly as a **reusable source-acquisition capability**:
`onion_source_discovery_and_acquisition`.
