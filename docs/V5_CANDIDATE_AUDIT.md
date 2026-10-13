# Vertical 5 Candidate Audit: Onion & Dark-Web Intelligence

**Audit Date**: October 2026  
**Auditor**: Vertical Recruitment Engineer, Heimdallr  
**Scope**: Open-Source Dark-Web Intelligence Engines & Upstream Projects  

---

## 1. Candidate Inventory & Assessment Matrix

| Candidate | Upstream Repository | Upstream License | Language / Architecture | Search Fit | Crawl Fit | License Decision | Recruitment Recommendation |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Ahmia** | `ahmia/ahmia-site` | BSD-3-Clause | Python / Django / Elasticsearch | **EXCELLENT** | POOR | **RECRUIT_WITH_RESTRICTIONS** | Recruit search engine adapter (BSD-3-Clause clean) |
| **TorBot** | `DedSecInside/TorBot` | GPL-3.0 | Python / Asyncio / BeautifulSoup | POOR | **EXCELLENT** | **REJECT / CLEAN_ROOM_ONLY** | Re-implement clean-room Apache-2.0 crawler |
| **OnionScan** | `s-rah/onionscan` | MIT / GPL-3.0 | Go / Concurrent Scanner | POOR | MODERATE | **REFERENCE_ONLY** | Unmaintained since 2018; reference architecture only |
| **DarkSearch** | Commercial API | Proprietary | REST API | MODERATE | NONE | **REJECT** | Deprecated / dead service; vendor lock-in |
| **Unified Clean-Room** | Native Heimdallr | Apache-2.0 | Python 3.12 / Clean-Room | **EXCELLENT** | **EXCELLENT** | **RECRUIT** | Primary production implementation (`impl_onion_integrated_v1`) |

---

## 2. In-Depth Candidate Audits

### Candidate 1: Ahmia (`ahmia/ahmia-site`)
- **Upstream Project**: Ahmia (Tor hidden service search engine, Finnish non-profit / Tor Project supported).
- **Repository**: `https://github.com/ahmia/ahmia-site`
- **License**: **BSD-3-Clause** (Permissive, commercial-friendly).
- **Dependencies**: Python, Django, Elasticsearch, Stem (Tor controller).
- **Maintenance Status**: Active, widely adopted as official Tor hidden service search gateway.
- **Data Source**: Continuous crawler submitting to Elasticsearch index with automated CSAM/abusive content filtering.
- **Capabilities**:
  - Search: Exceptional keyword matching across indexed `.onion` sites.
  - Discovery: Strong title and meta tag discovery.
  - Crawling: Minimal interactive crawling (relies on periodic batch backend).
  - Cryptographic Extraction: Limited (does not parse regex crypto wallets or PGP armor).
- **Network / Tor Requirements**: Requires local SOCKS5 proxy or Tor controller for direct fetches.
- **Legal & ToS Risks**: The public hosted service `ahmia.fi` enforces strict rate-limits and ToS against automated high-frequency scraping.
- **Architectural Decision**: **RECRUIT_WITH_RESTRICTIONS** (`impl_ahmia_search_v1`). The codebase is permissively licensed (BSD-3-Clause), but production deployment must operate against local indexes or respect rate-limits without violating `ahmia.fi` ToS.

---

### Candidate 2: TorBot (`DedSecInside/TorBot`)
- **Upstream Project**: TorBot (Darknet OSINT / link tree exploration tool).
- **Repository**: `https://github.com/DedSecInside/TorBot`
- **License**: **GPL-3.0** (**Strict Copyleft Incompatible**).
- **Dependencies**: Python, aiohttp, BeautifulSoup4, yattag.
- **Maintenance Status**: Moderately active community tool.
- **Data Source**: Live on-demand crawling via Tor SOCKS5 proxy.
- **Capabilities**:
  - Search: Poor (no global index; cannot search across unvisited hidden services).
  - Crawling: Excellent recursive link tree exploration.
  - Cryptographic Extraction: Strong regex extraction of Bitcoin, Monero, emails, and PGP blocks.
  - Topology: Maps mirror networks and replica nodes.
- **Legal & Licensing Gate**: **HARD ARCHITECTURAL CONSTRAINT**. GPL-3.0 is fundamentally incompatible with Heimdallr's Apache-2.0 core architecture. Incorporating TorBot code would cause copyleft contamination across Heimdallr.
- **Architectural Decision**: **REJECT DIRECT CODE / CLEAN_ROOM_ONLY**. All crawling, link tree exploration, and regex extraction logic must be authored strictly as a clean-room Apache-2.0 implementation (`impl_torbot_crawler_v1`) based only on specification and observable behavior.

---

### Candidate 3: OnionScan (`s-rah/onionscan`)
- **Upstream Project**: OnionScan (Security auditing tool for hidden services).
- **Repository**: `https://github.com/s-rah/onionscan`
- **License**: Mixed / GPL-3.0.
- **Language**: Go.
- **Maintenance Status**: Abandoned (last commit in 2018). Focuses on Tor v2 (16-char) addresses, which were deprecated by the Tor Project in 2021.
- **Architectural Decision**: **REFERENCE_ONLY**. Provides useful historical insights regarding server fingerprinting (Apache status pages, EXIF metadata), but cannot be recruited due to obsolescence and Go language impedance mismatch.

---

## 3. Coexistence Synthesis: The Unified Engine

The audit revealed that **Ahmia and TorBot do not compete directly; they provide strictly complementary capabilities**:
- Ahmia provides **global search and discovery** across thousands of indexed hidden services, but cannot crawl deep subpages or extract unstructured crypto addresses.
- TorBot provides **deep recursive crawling and extraction**, but cannot discover hidden services without an initial seed URL.

By developing the **Unified Clean-Room Onion Specialist (`impl_onion_integrated_v1`)**:
1. Ahmia search executes the initial discovery phase (`query -> top onion services`).
2. TorBot clean-room crawler traverses discovered services (`onion address -> crawled pages -> crypto/PGP extraction -> mirror clustering`).
3. Both are wrapped in `NormalizedObservation` with `is_authoritative = False` and clean Apache-2.0 licensing.

This achieves end-to-end dark-web intelligence with **zero license taint**.
