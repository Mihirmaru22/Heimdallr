# HEIMDALLR V3 — VERIFIED ARCHITECTURE & CAPABILITY AUDIT

**Target Platform**: Heimdallr (Evolved from Argus)  
**Audit Scope**: Repository Architecture, Source Code, Capabilities, Security Boundaries, Infrastructure, and Benchmarks  
**Audit Commit**: `56c62b5008219f558c89a79c34cd1bf5ec0f4d79` (`experiment/challenger-recruitment`)  
**Environment**: Linux x86_64, Python 3.12.3, Pytest 9.1.1 (445 tests passing in 16.99s)  
**Report Date**: October 2026  
**Auditor**: Independent Principal AI Systems Architect & Epistemic Verification Team  

---

## EXECUTIVE SUMMARY

Heimdallr (which evolved directly out of the Argus codebase) is an autonomous, hypothesis-driven intelligence research engine designed to investigate corporate, infrastructure, and identity targets across unstructured web content and structured domain fixtures. Originally engineered as an OSINT platform targeting United States automotive manufacturing plants, corporate leadership rosters, and SEC filings, the codebase has undergone architectural expansion toward a multi-specialist sovereign intelligence platform.

This technical audit establishes the **verified, code-backed reality** of Heimdallr V3. It distinguishes operational implementations from synthetic benchmark fixtures, evaluates actual versus claimed capabilities, audits model orchestration, traces security boundaries, and measures production readiness.

### Key Audit Findings

1. **Dual Architectural Reality**: The repository contains two distinct execution engines:
   - **Argus Classic Engine** ([`src/argus/core/controller.py`](file:///data/shared/project/PlayGround/Argus/src/argus/core/controller.py#L27-L620)): A production crawler-and-verifier pipeline featuring Crawlee, Playwright, HTTPX streaming, BeautifulSoup extraction, Laya neural candidate triage, and an LLM-backed Epistemic Verifier. On the real-world, dirty-web benchmark (**Eval V1 Core 11 tasks**), it achieves a **45.5% pass rate**, with **50.0% field accuracy** and **13.5% entity precision** (burdened by 86.5% noise entities from open web crawling).
   - **Heimdallr V2/V3 Investigation Engine** ([`src/argus/investigation/orchestrator.py`](file:///data/shared/project/PlayGround/Argus/src/argus/investigation/orchestrator.py#L46-L742)): A graph-based, hypothesis-driven orchestrator operating with specialist adapters (Corporate, Infrastructure, Identity, Sanctions, Onion). While it scores **100.0% (120/120)** on the frozen Eval V2 benchmark, **this evaluation runs exclusively against an in-memory synthetic fixture corpus** ([`CORPUS_V2_REGISTRY`](file:///data/shared/project/PlayGround/Argus/src/argus/evals/v2/corpus.py)). Furthermore, the engine contains **explicit, hard-coded regular expressions and entity routing rules** in [`orchestrator.py`](file:///data/shared/project/PlayGround/Argus/src/argus/investigation/orchestrator.py#L375-L413) tailored specifically to the benchmark scenarios (`AeroDynamics`, `Apex Technologies`, `Rachel Thorne`, `Elena Rostova`, `David Marcus`).
2. **Model Orchestration & The "JEV" Myth**:
   - The primary generative LLM layer is implemented exclusively in [`src/argus/llm/openrouter.py`](file:///data/shared/project/PlayGround/Argus/src/argus/llm/openrouter.py#L61-L163) calling `deepseek/deepseek-chat` via the OpenRouter HTTP API.
   - Fast, non-autoregressive snippet and document triage (~33ms single-forward pass) is powered by **Laya** ([`src/argus/brain/system1.py`](file:///data/shared/project/PlayGround/Argus/src/argus/brain/system1.py#L22-L566), `convaiinnovations/laya`).
   - **"JEV" does not exist anywhere in the repository** (0 code occurrences, 0 documentation occurrences). It is completely non-existent.
   - There are **no local LLM runtimes** (no vLLM, Ollama, or llama.cpp integrations).
3. **Severe Gap in Document Intelligence**:
   - Despite documentation claims of "PDF/HTML document extraction" ([`docs/V3_1_REGRESSION_REPORT.md:47`](file:///data/shared/project/PlayGround/Argus/docs/V3_1_REGRESSION_REPORT.md#L47)), **PDF processing is completely non-existent**. No PDF extraction libraries (`pypdf`, `pdfplumber`, `pymupdf`) exist in [`pyproject.toml`](file:///data/shared/project/PlayGround/Argus/pyproject.toml). Binary PDF files fetched by the crawler fail extraction or are logged as unreadable binary streams ([`data/exports/events.csv:379`](file:///data/shared/project/PlayGround/Argus/data/exports/events.csv#L379)).
4. **Specialist Emulation vs. Live Reality**:
   - The Dark-Web/Onion specialist ([`src/argus/specialists/onion/`](file:///data/shared/project/PlayGround/Argus/src/argus/specialists/onion/)) and Sanctions specialist ([`src/argus/specialists/sanctions/`](file:///data/shared/project/PlayGround/Argus/src/argus/specialists/sanctions/)) do **not** connect to live Tor SOCKS5 daemons or live yente/OpenSanctions API servers. They perform in-memory lookups against static Python dictionaries (`ONION_CORPUS` and `SANCTIONS_CORPUS`).
   - The Blackbird specialist ([`src/argus/specialists/blackbird_specialist.py`](file:///data/shared/project/PlayGround/Argus/src/argus/specialists/blackbird_specialist.py#L42-L91)) simulates network checks against an in-memory dictionary, hard-coding `total_sites_checked=max(checked_count, 150)`.
5. **Genuinely Strong Engineering Assets**:
   - **Epistemic Invariant Enforcement**: The `ExpertVerifier` ([`src/argus/verifier/engine.py`](file:///data/shared/project/PlayGround/Argus/src/argus/verifier/engine.py#L114-L444)) strictly prevents inferred claims from being promoted to verified facts and requires multiple independent content hashes or canonical domains before declaring corroboration.
   - **Syndication Intelligence**: Source independence clustering ([`src/argus/verifier/syndication_intelligence.py`](file:///data/shared/project/PlayGround/Argus/src/argus/verifier/syndication_intelligence.py#L48-L129)) correctly discounts wire-service duplicates (`prnewswire.com`, `businesswire.com`).
   - **SSRF & Route Interception**: Bulletproof network safety ([`src/argus/search/pipeline.py:95-150`](file:///data/shared/project/PlayGround/Argus/src/argus/search/pipeline.py#L95-L150) and [`src/argus/crawler/fetcher.py:257-270`](file:///data/shared/project/PlayGround/Argus/src/argus/crawler/fetcher.py#L257-L270)) blocking private IPs, loopbacks, DNS rebinding, and cloud metadata services across both HTTPX and Playwright.
   - **Adversarial Security Gate**: Robust input/output defusing ([`src/argus/competition/security_gate.py`](file:///data/shared/project/PlayGround/Argus/src/argus/competition/security_gate.py#L33-L218)) neutralizing prompt injections, shell injection strings, path traversal, and evaluator tampering.

---

## 1. SYSTEM IDENTITY & CURRENT MATURITY

### 1.1 What Exactly is Heimdallr?
Heimdallr is an asynchronous, multi-agent investigative research framework built in Python 3.12. It combines search query formulation, web discovery, dual-tier web crawling (HTTPX + Playwright), document parsing, neural candidate triage, and structured epistemic verification.

Originally conceived as **Argus**, an automated competitive intelligence system for profiling commercial enterprises (specifically US automotive assembly plants, plant directors, technical leads, and SEC filings), it was renamed and architecturally refactored into **Heimdallr** to support multi-domain investigative workflows (corporate registries, technical infrastructure/DNS/CT logs, identity attribution, international sanctions, and dark web tracking).

### 1.2 What Problem Does It Currently Solve?
In its current operational state, Heimdallr solves:
1. **Semi-Automated Corporate Dossier Generation**: Given a target company or executive, it searches the open web (via DuckDuckGo, Google News, or SearXNG), crawls candidate pages, extracts leadership and facility information, and aggregates the results into a structured SQLite database.
2. **Deterministic Multi-Hop Graph Traversal over Pre-Curated Intelligence**: Within its synthetic benchmark harness, it demonstrates how corporate entities can be linked to digital infrastructure (domains, CT logs), identity profiles (executives, developer handles), and sanctions lists.

### 1.3 Actual Operational Capabilities vs. Stated Goals
- **Operational Today**: Live web search via DuckDuckGo and Google News; two-tier crawling with JavaScript execution via Playwright; HTML table extraction into Markdown; neural relevance filtering via Laya System 1; claim-level verification and contradiction detection via LLM adjudication; strict SSRF and prompt-injection sanitization.
- **Partially Implemented**: LinkedIn SERP scraping (relies entirely on search engine snippet dorking; no direct session login or graph navigation); 4chan OSINT (queries live `/o/` and `/biz/` JSON catalog APIs, but hardcoded to automotive and finance boards).
- **Synthetic / Emulated**: Tor/Onion intelligence, OpenSanctions/PEP screening, and Blackbird cross-platform identity probing. These do not execute live external investigations; they query in-memory Python dictionaries.
- **Non-Existent**: PDF document ingestion, sovereign air-gapped local LLM inference, multi-lingual translation pipelines, enterprise document repository connectors, and distributed task queues.

### 1.4 Development Stage
**Stage: Advanced Working Prototype / Research Testbed (TRL 4–5).**  
The core architecture contains production-grade data models and verifier mechanics, but the investigation orchestrator is heavily coupled to synthetic evaluation benchmarks, and its background scaling infrastructure relies on single-node SQLite and in-process `asyncio`.

### 1.5 Component Maturity Inventory

| Component | Maturity Level | Primary File Location | Verification Notes |
| :--- | :---: | :--- | :--- |
| **Search Pipeline & SSRF Guard** | **Fully Functional** | [`src/argus/search/pipeline.py`](file:///data/shared/project/PlayGround/Argus/src/argus/search/pipeline.py) | Active DNS resolution, IP filtering, metadata blocking, URL normalization. |
| **Two-Tier Fetcher (HTTPX + Playwright)** | **Fully Functional** | [`src/argus/crawler/fetcher.py`](file:///data/shared/project/PlayGround/Argus/src/argus/crawler/fetcher.py) | Streamed 5MB limit, Playwright route interception, anti-bot browser escalation. |
| **Document Extractor (HTML)** | **Fully Functional** | [`src/argus/crawler/extractor.py`](file:///data/shared/project/PlayGround/Argus/src/argus/crawler/extractor.py) | High quality HTML boilerplate stripping, table-to-markdown conversion. |
| **System 1 Engine (Laya)** | **Fully Functional** | [`src/argus/brain/system1.py`](file:///data/shared/project/PlayGround/Argus/src/argus/brain/system1.py) | Non-autoregressive neural scoring (~33ms), graceful heuristic fallback. |
| **Epistemic Verifier Engine** | **Fully Functional** | [`src/argus/verifier/engine.py`](file:///data/shared/project/PlayGround/Argus/src/argus/verifier/engine.py) | Enforces evidence grounding, independent sources, and contradiction detection. |
| **Syndication Intelligence** | **Fully Functional** | [`src/argus/verifier/syndication_intelligence.py`](file:///data/shared/project/PlayGround/Argus/src/argus/verifier/syndication_intelligence.py) | Content-hash and wire-domain clustering preventing duplicate corroboration. |
| **Security Gate & Injection Defuser** | **Fully Functional** | [`src/argus/competition/security_gate.py`](file:///data/shared/project/PlayGround/Argus/src/argus/competition/security_gate.py) | AST code auditor and 12-vector regex payload defuser. |
| **Classic Controller (Argus)** | **Fully Functional** | [`src/argus/core/controller.py`](file:///data/shared/project/PlayGround/Argus/src/argus/core/controller.py) | End-to-end autonomous crawler-worker-verifier loop for live web targets. |
| **Investigation Engine (V2/V3)** | **Partially Functional** | [`src/argus/investigation/orchestrator.py`](file:///data/shared/project/PlayGround/Argus/src/argus/investigation/orchestrator.py) | Hypothesis graph works, but contains hardcoded scenario regexes (lines 375–413). |
| **Corporate Specialist** | **Experimental** | [`src/argus/specialists/corporate/specialist.py`](file:///data/shared/project/PlayGround/Argus/src/argus/specialists/corporate/specialist.py) | Mix of heuristics and synthetic corpus search; lacks live SEC EDGAR API client. |
| **Infrastructure Specialist** | **Experimental** | [`src/argus/specialists/infrastructure/`](file:///data/shared/project/PlayGround/Argus/src/argus/specialists/infrastructure/) | Simulates CT log / DNS reconnaissance; no live crt.sh or massdns socket workers. |
| **Identity Specialist** | **Experimental** | [`src/argus/specialists/identity/`](file:///data/shared/project/PlayGround/Argus/src/argus/specialists/identity/) | Graph-based identifier correlation, but operates on mock fixtures. |
| **Blackbird Specialist** | **Incomplete / Mock** | [`src/argus/specialists/blackbird_specialist.py`](file:///data/shared/project/PlayGround/Argus/src/argus/specialists/blackbird_specialist.py) | Simulates platform checks across an in-memory dictionary; hardcodes site counts. |
| **Sanctions Specialist** | **Incomplete / Mock** | [`src/argus/specialists/sanctions/specialist.py`](file:///data/shared/project/PlayGround/Argus/src/argus/specialists/sanctions/specialist.py) | Operates on static 137-line dictionary `SANCTIONS_CORPUS`; no live Yente connection. |
| **Onion Specialist** | **Incomplete / Mock** | [`src/argus/specialists/onion/`](file:///data/shared/project/PlayGround/Argus/src/argus/specialists/onion/) | Operates on static `ONION_CORPUS`; no Tor SOCKS5 proxy or circuit logic exists. |
| **Document Intelligence (PDF)** | **Non-Existent** | *Missing* | Zero PDF parsing dependencies or modules in the entire codebase. |
| **JEV Decision Engine** | **Non-Existent** | *Missing* | Zero occurrences across the entire repository. |

### 1.6 What Distinguishes V3 from Previous Versions?
- **Argus V1**: Single-purpose automotive OSINT crawler with hardcoded manufacturing entity models, SEC scraping, and plant leadership matrix materialization.
- **Argus V2 / OpenPlanter Absorption**: Integrated OpenPlanter-style explicit subtask acceptance criteria, bounded query budgeting ([`src/argus/brain/planner_v2.py`](file:///data/shared/project/PlayGround/Argus/src/argus/brain/planner_v2.py)), and Laya System 1 neural ranking.
- **Heimdallr V3**: Introduces the `CapabilityRegistry` ([`src/argus/capability_registry/registry.py`](file:///data/shared/project/PlayGround/Argus/src/argus/capability_registry/registry.py)), candidate specialist recruitment, security gating (`SecurityGateValidator`), temporal state reasoning (`TemporalStateReasoner`), and cross-specialist chaining (Corporate -> Infrastructure -> Identity -> Sanctions).

---

## 2. COMPLETE ARCHITECTURE

### 2.1 Reconstructed Execution Pipeline

```mermaid
flowchart TD
    subgraph Input_and_Planning [1. Task Ingestion & Planning]
        UserReq["User Objective / Contract"] --> PlanSelect{"Execution Path"}
        PlanSelect -->|Classic Web Path| ArgusBrain["ArgusPlannerV2 / ResearchBrain"]
        PlanSelect -->|Investigation Path| InvPlan["InvestigationPlanner"]
        ArgusBrain --> DynamicBudget["Laya System 1 Budget & Depth Calibration"]
        InvPlan --> QuestionGraph["Question Dependency DAG & Hypotheses"]
    end

    subgraph Search_and_Discovery [2. Search & Candidate Triage]
        DynamicBudget --> QueryGen["Search Query & Dork Formulation"]
        QuestionGraph --> ActionDispatch["Action Dispatcher (_dispatch_action)"]
        QueryGen --> SearchPipe["SearchPipeline (SSRF Guard & URL Normalizer)"]
        SearchPipe --> Providers["Search Providers: DuckDuckGo / SearXNG / 4chan / Google News"]
        Providers --> SnippetTriage["Laya System 1 Snippet Triage (~33ms non-autoregressive)"]
    end

    subgraph Crawling_and_Extraction [3. Ingestion & Document Processing]
        SnippetTriage --> CrawlQueue["Crawlee RequestQueue"]
        CrawlQueue --> TwoTier["TwoTierFetcher"]
        TwoTier -->|Tier 1: Fast HTTP| HttpxClient["HTTPX Stream (5MB Ceiling)"]
        TwoTier -->|Tier 2: Escalation| PlaywrightClient["Playwright Headless Chromium (Route Interception)"]
        HttpxClient --> DocExtract["DocumentExtractor (BeautifulSoup HTML & Markdown Tables)"]
        PlaywrightClient --> DocExtract
        DocExtract --> DocTriage["Laya System 1 Document Relevance Filter"]
    end

    subgraph Specialist_Execution [4. Specialist Layer (Heimdallr V3 Path)]
        ActionDispatch --> CapRegistry["CapabilityRegistry"]
        CapRegistry --> SpecRouter{"Specialist Router"}
        SpecRouter --> CorpSpec["Corporate Specialist (Fixtures / Heuristics)"]
        SpecRouter --> InfraSpec["Infrastructure Specialist (CT / DNS Simulation)"]
        SpecRouter --> IdentSpec["Identity Specialist (Personas / Handles)"]
        SpecRouter --> SancSpec["Sanctions Specialist (In-Memory Corpus)"]
        SpecRouter --> OnionSpec["Onion Specialist (In-Memory Mock)"]
        CorpSpec & InfraSpec & IdentSpec & SancSpec & OnionSpec --> SecGate["SecurityGateValidator (Defuse Injections & Epistemic Demotion)"]
    end

    subgraph Evidence_and_Verification [5. Epistemic Verification & Knowledge State]
        DocTriage --> WorkerEng["WorkerEngine (Extract Claims & Entities via DeepSeek LLM)"]
        SecGate --> InvState["InvestigationState (Belief Topology & Audit Trail)"]
        WorkerEng --> RepoStg[("SQLite Repository")]
        RepoStg --> Verifier["ExpertVerifier (Epistemic Alignment & Grounding Check)"]
        Verifier --> SyndIntel["SyndicationIntelligence (Content-Hash De-duplication)"]
        Verifier --> TempReason["TemporalStateReasoner (Lifecycle Supersession)"]
        Verifier --> LLMAdj["LLM Adjudication (DeepSeek Structured JSON via OpenRouter)"]
        LLMAdj --> Disambig{"Contradiction Detected?"}
        Disambig -->|Yes| SpawnTask["Spawn Disambiguation Subtask"]
        Disambig -->|No| StoreClaims["Commit SUPPORTED / CORROBORATED Claims"]
    end

    subgraph Output_and_Storage [6. Dossier Synthesis & Snapshot]
        StoreClaims --> FinalDossier["ResearchDossier / Materialized Matrix"]
        InvState --> StoreSnapshot["InvestigationStore (JSON/JSONL Snapshots)"]
        SpawnTask --> ArgusBrain
    end
```

### 2.2 Component Deep-Dive

#### 1. Controller & Orchestration Core
- **Implementation**: [`src/argus/core/controller.py`](file:///data/shared/project/PlayGround/Argus/src/argus/core/controller.py) (`ArgusController`) and [`src/argus/investigation/orchestrator.py`](file:///data/shared/project/PlayGround/Argus/src/argus/investigation/orchestrator.py) (`InvestigationEngine`).
- **Responsibilities**: Manages task lifecycle transitions, invokes planning, dispatches crawler jobs, checks stopping criteria, and triggers the verifier.
- **Dependencies**: `asyncio`, `logging`, `pydantic`.
- **Inputs & Outputs**: Input: `ResearchObjective` or text query; Output: `ResearchDossier`, `InvestigationState`, SQLite rows.
- **Error Handling**: `try/except` wraps around task execution in `ArgusController.run` ([lines 414–450](file:///data/shared/project/PlayGround/Argus/src/argus/core/controller.py#L414-L450)); tasks failing transition to `TaskStatus.FAILED`, with automated requeuing up to `max_retries` (default 3).
- **Bottlenecks**: `ArgusController` runs tasks serially in a single-threaded `while` loop ([lines 121–451](file:///data/shared/project/PlayGround/Argus/src/argus/core/controller.py#L121-L451)). Tasks are not executed concurrently across parallel workers.

#### 2. Planning Subsystem
- **Implementation**: [`src/argus/brain/planner_v2.py`](file:///data/shared/project/PlayGround/Argus/src/argus/brain/planner_v2.py) (`ArgusPlannerV2`) and [`src/argus/investigation/planner.py`](file:///data/shared/project/PlayGround/Argus/src/argus/investigation/planner.py) (`InvestigationPlanner`).
- **Responsibilities**: Decomposes top-level goals into subtasks with explicit acceptance criteria, search queries, and expected entity schemas.
- **Dependencies**: Laya (for difficulty/depth calibration), Pydantic.
- **Inputs & Outputs**: Input: `ResearchObjective`; Output: List of `ResearchTask` or `InvestigationQuestion` objects.
- **Status**: Implemented and verified. Absorbed OpenPlanter's bounded search budget and acceptance criteria.

#### 3. Search & Discovery Subsystem
- **Implementation**: [`src/argus/search/pipeline.py`](file:///data/shared/project/PlayGround/Argus/src/argus/search/pipeline.py) (`SearchPipeline`).
- **Responsibilities**: Dispatches queries to search backends, normalizes URLs (stripping UTM codes and unwrapping redirects), and filters malicious destinations.
- **Providers Available**:
  - `DuckDuckGoSearchProvider` ([`src/argus/search/duckduckgo.py`](file:///data/shared/project/PlayGround/Argus/src/argus/search/duckduckgo.py)): Live organic web search using `ddgs`. Concurrency locked to 2 with 0.5s rate-limit interval.
  - `SearXNGSearchProvider` ([`src/argus/search/searxng.py`](file:///data/shared/project/PlayGround/Argus/src/argus/search/searxng.py)): Connects to a local SearXNG meta-search instance (`http://localhost:8080`).
  - `FourChanSearchProvider` ([`src/argus/search/fourchan.py`](file:///data/shared/project/PlayGround/Argus/src/argus/search/fourchan.py)): Directly queries 4chan read API for `/o/` and `/biz/`.
  - `LinkedInSearchProvider` ([`src/argus/search/linkedin.py`](file:///data/shared/project/PlayGround/Argus/src/argus/search/linkedin.py)): Generates `site:linkedin.com/in` dorks and parses organic SERP titles via regex.
  - `PhotonAdapter` ([`src/argus/search/photon_adapter.py`](file:///data/shared/project/PlayGround/Argus/src/argus/search/photon_adapter.py)): Challenger regex link harvester.
- **Error Handling**: Graceful network timeouts; failed queries return empty `SearchResponse`.

#### 4. Crawling & Document Ingestion
- **Implementation**: [`src/argus/crawler/fetcher.py`](file:///data/shared/project/PlayGround/Argus/src/argus/crawler/fetcher.py) (`TwoTierFetcher`) and [`src/argus/crawler/engine.py`](file:///data/shared/project/PlayGround/Argus/src/argus/crawler/engine.py) (`CrawlExecutionEngine`).
- **Responsibilities**: Acquires raw web pages. Executes Tier 1 (HTTPX streaming GET) first; if HTTP fails or HTML contains JS-shell indicators (e.g., "enable javascript"), escalates to Tier 2 (headless Chromium via Playwright).
- **Safety Limits**: Streaming aborts if `Content-Length` or streamed bytes exceed 5 MB (`MAX_RESPONSE_BYTES`). Playwright context route interception drops fonts, media, and unapproved redirect URLs.
- **Status**: Implemented, robust, and verified.

#### 5. Content Extraction
- **Implementation**: [`src/argus/crawler/extractor.py`](file:///data/shared/project/PlayGround/Argus/src/argus/crawler/extractor.py) (`DocumentExtractor`).
- **Responsibilities**: Strips scripts, navigation, footers, cookie banners, and GDPR modals using BeautifulSoup. Parses HTML tables into Markdown tables, extracts JSON-LD metadata, OpenGraph tags, and canonical URLs.
- **Limitations**: Only parses HTML. Completely lacks PDF, DOCX, or OCR extractors.

#### 6. Worker & Entity Extraction Layer
- **Implementation**: [`src/argus/worker/engine.py`](file:///data/shared/project/PlayGround/Argus/src/argus/worker/engine.py) (`WorkerEngine`).
- **Responsibilities**: Segments substantive text, builds extraction prompts, invokes the LLM via `generate_structured`, extracts candidate `Entity` and `Claim` objects, and inserts them into SQLite as `ClaimStatus.PENDING`.
- **Status**: Fully functional with structured Pydantic response models.

#### 7. Epistemic Verifier Subsystem
- **Implementation**: [`src/argus/verifier/engine.py`](file:///data/shared/project/PlayGround/Argus/src/argus/verifier/engine.py) (`ExpertVerifier`), [`src/argus/verifier/syndication_intelligence.py`](file:///data/shared/project/PlayGround/Argus/src/argus/verifier/syndication_intelligence.py) (`SyndicationIntelligence`), and [`src/argus/verifier/temporal_reasoner.py`](file:///data/shared/project/PlayGround/Argus/src/argus/verifier/temporal_reasoner.py) (`TemporalStateReasoner`).
- **Responsibilities**: Groups pending claims by `(subject, predicate)`. Enforces strict token-level alignment between claim values and raw evidence passages. Uses `SyndicationIntelligence` to detect syndicated news mirrors. Employs fast-path heuristic corroboration for uncontested agreeing claims; invokes LLM adjudication for conflicting or ambiguous claims.
- **Status**: Excellent architecture; adheres strictly to epistemic invariants.

### 2.3 Architectural Bottlenecks & Single Points of Failure
1. **Single-Threaded Investigation Loop**: Both `ArgusController` and `InvestigationEngine` process one action/task at a time. Concurrency is limited to the Crawlee page batch processor.
2. **SQLite Concurrency Contention**: SQLite is used in WAL mode ([`src/argus/storage/db.py:27`](file:///data/shared/project/PlayGround/Argus/src/argus/storage/db.py#L27)), but write locks still serialize state updates. Investigations scaling to thousands of sources will suffer database lock timeouts.
3. **External API Dependence**: The system depends on OpenRouter for all generative intelligence. Network latency to OpenRouter (often 2–5 seconds per structured call) dominates end-to-end task duration.
4. **Hardcoded Benchmark Routing**: In [`src/argus/investigation/orchestrator.py:375-413`](file:///data/shared/project/PlayGround/Argus/src/argus/investigation/orchestrator.py#L375-L413), multi-specialist chaining is hard-wired via regex strings for specific target entities. If an unknown entity is investigated, these automatic multi-hop chains fail to trigger unless generalist fallback queries succeed.

---

## 3. MODELS & INTELLIGENCE ORCHESTRATION

### 3.1 Model Inventory & Assignments

| Role / Component | Technology / Model | Provider / Engine | Local vs. Remote | Responsibilities |
| :--- | :--- | :--- | :--- | :--- |
| **Generative LLM (Core)** | `deepseek/deepseek-chat` | OpenRouter HTTP API | Remote (OpenRouter) | Structured entity extraction, claim formulation, verifier adjudication. |
| **System 1 Triage Router** | Laya (`convaiinnovations/laya`) | PyTorch CPU runtime | Local (in-process) | Snippet ranking, document noise gating, task difficulty calibration (~33ms). |
| **JEV Engine** | **NON-EXISTENT** | **None** | **N/A** | Claimed in architectural discussions; zero code exists. |
| **Local LLMs (vLLM/Ollama)**| **NON-EXISTENT** | **None** | **N/A** | No local generative models integrated. |

### 3.2 Generative LLM Integration & OpenRouter Implementation
The sole remote LLM integration is implemented in [`src/argus/llm/openrouter.py`](file:///data/shared/project/PlayGround/Argus/src/argus/llm/openrouter.py#L61-L163) (`OpenRouterLLMProvider`):
- **Base URL**: `https://openrouter.ai/api/v1`
- **Default Model**: `deepseek/deepseek-chat` ([line 67](file:///data/shared/project/PlayGround/Argus/src/argus/llm/openrouter.py#L67))
- **Authentication**: Inspects `OPENROUTER_API_KEY` or `OPEN_ROUTER_API` environment variables, or reads `docs/.env` / `.env` ([lines 71–90](file:///data/shared/project/PlayGround/Argus/src/argus/llm/openrouter.py#L71-L90)).
- **Structured Output Strategy**:
  - Employs Pydantic `model_json_schema()` injected directly into the system prompt ([lines 103–109](file:///data/shared/project/PlayGround/Argus/src/argus/llm/openrouter.py#L103-L109)).
  - Passes payload parameter: `"response_format": {"type": "json_object"}` ([line 132](file:///data/shared/project/PlayGround/Argus/src/argus/llm/openrouter.py#L132)).
  - Output parsing runs through `extract_json_payload` ([lines 15–58](file:///data/shared/project/PlayGround/Argus/src/argus/llm/openrouter.py#L15-L58)), which searches for markdown code fences (````json ... ````), extracts outermost matching curly braces (`{...}`), and validates via Pydantic `model_validate_json(clean_json)` ([line 162](file:///data/shared/project/PlayGround/Argus/src/argus/llm/openrouter.py#L162)).
- **Retries & Backoff**: Retries 3 times on HTTP `429`, `502`, `503`, and `504` status codes with exponential backoff (`sleep_time = backoff_delay * 2**attempt`) or parses the `Retry-After` header ([lines 135–153](file:///data/shared/project/PlayGround/Argus/src/argus/llm/openrouter.py#L135-L153)).

### 3.3 System 1 Non-Autoregressive Decision Engine (Laya)
Implemented in [`src/argus/brain/system1.py`](file:///data/shared/project/PlayGround/Argus/src/argus/brain/system1.py):
- **Purpose**: Fast (~33ms) non-autoregressive triage to prune irrelevant snippets and noisy boilerplate web pages before spending slow, costly tokens on LLMs.
- **Operational Tasks**:
  1. `triage_search_results` ([lines 64–133](file:///data/shared/project/PlayGround/Argus/src/argus/brain/system1.py#L64-L133)): Evaluates whether search snippets contain factual operational details relevant to the task.
  2. `triage_document` ([lines 135–205](file:///data/shared/project/PlayGround/Argus/src/argus/brain/system1.py#L135-L205)): Scores substantive relevance of crawled document text before passing it to `WorkerEngine`.
  3. `calibrate_budget_and_depth` ([lines 405–471](file:///data/shared/project/PlayGround/Argus/src/argus/brain/system1.py#L405-L471)): Dynamically adjusts max tasks (3–12) and crawl depth (1–3) based on query complexity.
- **Fallback Mechanism**: If the `laya` package fails to import or the model fails to load, `self._is_available` is set to `False` and the engine automatically falls back to deterministic rule-based keyword heuristics ([lines 49–55, 80–82, 149–153](file:///data/shared/project/PlayGround/Argus/src/argus/brain/system1.py#L49-L55)).

### 3.4 Model Swappability & Portability
Heimdallr abstracts model execution behind `LLMProvider` ([`src/argus/llm/provider.py`](file:///data/shared/project/PlayGround/Argus/src/argus/llm/provider.py#L9-L21)):
```python
class LLMProvider(ABC):
    @abstractmethod
    async def generate_structured(self, prompt: str, response_model: type[T], system_prompt: str | None = None, temperature: float = 0.0) -> T: ...
```
Replacing `deepseek/deepseek-chat` with another model hosted on OpenRouter (e.g. `anthropic/claude-3.5-sonnet`, `meta-llama/llama-3.3-70b-instruct`) requires only changing the `model` constructor parameter. However, running fully local inference would require implementing a custom `vLLMProvider` or `OllamaProvider` conforming to this contract.

---

## 4. RESEARCH & INFORMATION ACQUISITION

### 4.1 Acquisition Subsystems Audit

#### Search Engines & Discovery
- **DuckDuckGo**: Functional via `ddgs`. No API key required. Rate-limited to max 2 concurrent calls.
- **SearXNG**: Functional via HTTP JSON calls to a configured instance.
- **4chan API**: Connects to `a.4cdn.org/o/catalog.json` and `a.4cdn.org/biz/catalog.json`. Live, but hardcoded to those two boards.
- **LinkedIn**: Bypasses the login authwall by executing DuckDuckGo search dorks (`site:linkedin.com/in "<name>" "<company>"`) and parsing organic SERP titles via regex.
- **Google News**: Scrapes RSS / XML feeds for corporate announcements.
- **Photon**: Regex link crawler for endpoint discovery.

#### Crawling & Browser Automation
- **HTTP Tier (HTTPX)**: Asynchronous streaming client. Drops responses larger than 5 MB.
- **Browser Tier (Playwright)**: Headless Chromium. Intercepts all sub-resource routes to block media/fonts and enforce SSRF boundaries. Triggers on anti-bot protection or SPA javascript-only shells.

#### Content Extraction & Parsing
- **HTML**: Strips boilerplate, navigations, footers, forms, and cookie banners using BeautifulSoup. Converts tables to clean Markdown format.
- **PDF & Document Processing**: **NON-EXISTENT**. If a crawler fetches an official government filing, academic whitepaper, or corporate ESG report formatted as a PDF, it cannot parse it. In test logs and production database exports ([`data/exports/events.csv:379`](file:///data/shared/project/PlayGround/Argus/data/exports/events.csv#L379)), the engine explicitly records:
  > `"The provided source is a binary PDF stream with no readable text. It contains no substantive facts..."`

#### Multilingual Research Capabilities
- Heimdallr has **no dedicated multi-lingual tokenization, entity translation, or cross-lingual linking pipeline**.
- It relies solely on the inherent multilingual capability of the underlying LLM (DeepSeek) and Laya's multilingual embeddings. It cannot systematically query Russian, Chinese, or Arabic registries in their native alphabets unless queries are pre-translated.

### 4.2 Research Restrictions & Constraints Inventory

| Restriction | Implemented Location | Hard-Coded vs. Configurable | Origin / Rationale |
| :--- | :--- | :---: | :--- |
| **SSRF Disallowed Hosts** | [`src/argus/search/pipeline.py:9-15`](file:///data/shared/project/PlayGround/Argus/src/argus/search/pipeline.py#L9-L15) | Hard-coded | Security Control: Blocks `localhost`, `127.0.0.1`, `::1`, `169.254.169.254`, `metadata.google.internal`. |
| **SSRF Internal TLDs** | [`src/argus/search/pipeline.py:114-117`](file:///data/shared/project/PlayGround/Argus/src/argus/search/pipeline.py#L114-L117) | Hard-coded | Security Control: Blocks `.local`, `.internal`, `.localhost`, `.lan`, `.home`, `.corp`, `.arpa`. |
| **Max Response Size** | [`src/argus/crawler/fetcher.py:11`](file:///data/shared/project/PlayGround/Argus/src/argus/crawler/fetcher.py#L11) | Hard-coded (5 MB) | Resource Guard: Prevents memory exhaustion / DoS from large binary downloads. |
| **DuckDuckGo Concurrency** | [`src/argus/search/duckduckgo.py:27-28`](file:///data/shared/project/PlayGround/Argus/src/argus/search/duckduckgo.py#L27-L28) | Configurable (Default 2) | Provider Constraint: Prevents IP blacklisting and HTTP 429 rate limits by DuckDuckGo. |
| **Crawl Pages Per Task** | [`src/argus/core/controller.py:61`](file:///data/shared/project/PlayGround/Argus/src/argus/core/controller.py#L61) | Configurable (Default 3) | Budget Control: Restricts number of candidate URLs crawled per subtask. |
| **Diminishing Yield Stop**| [`src/argus/core/controller.py:132`](file:///data/shared/project/PlayGround/Argus/src/argus/core/controller.py#L132) | Hard-coded (3 zero-yield) | Architectural Control: Halts investigation if 3 consecutive tasks yield zero new claims. |
| **Max Evidence Per Claim**| [`src/argus/verifier/engine.py:14`](file:///data/shared/project/PlayGround/Argus/src/argus/verifier/engine.py#L14) | Hard-coded (10 items) | Token Budget: Limits evidence citations passed into LLM adjudication prompt. |
| **Sanctions & Onion Scope**| [`src/argus/specialists/`](file:///data/shared/project/PlayGround/Argus/src/argus/specialists/) | Hard-coded in fixtures | Architectural Incompleteness: Restricted to mock entities in static corpus files. |

---

## 5. EVIDENCE, KNOWLEDGE & INTELLIGENCE

### 5.1 Claim-Level Evidence Provenance
Heimdallr implements an explicit, rigorous data model for epistemic provenance:
- **`Document`** ([`src/argus/crawler/models.py`](file:///data/shared/project/PlayGround/Argus/src/argus/crawler/models.py)): Stores `url`, `canonical_url`, `title`, `text_content`, `published_at`, `status_code`, and `fetch_method`.
- **`Evidence`** ([`src/argus/domain/evidence.py`](file:///data/shared/project/PlayGround/Argus/src/argus/domain/evidence.py)): Records the exact verbatim `passage`, character offsets (`start_offset`, `end_offset`), source URL, document ID, and `content_hash`.
- **`Claim`** ([`src/argus/domain/claim.py`](file:///data/shared/project/PlayGround/Argus/src/argus/domain/claim.py)): Stores triples `(subject_entity_id, predicate, object_value)` linked directly to a list of `evidence_ids`. Claims track epistemic statuses: `PENDING`, `SUPPORTED`, `CORROBORATED`, `CONTRADICTED`, `REFUTED`, `INFERRED`, or `UNVERIFIED`.

### 5.2 Source Independence & Syndication Intelligence
A critical strength of Heimdallr is its explicit enforcement of the epistemic rule:  
$$\text{3 syndicated mirrors of the same press release} \neq \text{3 independent sources}.$$

In [`src/argus/verifier/syndication_intelligence.py`](file:///data/shared/project/PlayGround/Argus/src/argus/verifier/syndication_intelligence.py), the engine:
1. Clusters incoming URLs by domain and content hash (`hashlib.sha256(text.encode())`).
2. Checks against a built-in registry of known commercial wire services: `prnewswire.com`, `businesswire.com`, `globenewswire.com`, `marketwatch.com`, `accesswire.com`, `benzinga.com` ([lines 51–59](file:///data/shared/project/PlayGround/Argus/src/argus/verifier/syndication_intelligence.py#L51-L59)).
3. Deduplicates multiple copies originating from the same wire cluster into a single independent observation cluster.

### 5.3 Grounding Validation & Contradiction Detection
Before any claim can be promoted to `SUPPORTED` or `CORROBORATED`:
1. **Passage-Level Grounding Check** ([`src/argus/verifier/engine.py:18-112`](file:///data/shared/project/PlayGround/Argus/src/argus/verifier/engine.py#L18-L112)): `check_claim_evidence_alignment` verifies that non-stopword tokens from both the subject entity name and the object value exist verbatim in the cited evidence passage. If an LLM hallucinated a relation not present in the excerpt, it is rejected.
2. **Contradiction Detection**: When multiple claims exist for the same `(subject, predicate)` with conflicting `object_value` strings (e.g. two different people claimed as Plant Director), the fast path is bypassed, and the claims are sent to the `ExpertVerifier` adjudication prompt ([lines 318–328](file:///data/shared/project/PlayGround/Argus/src/argus/verifier/engine.py#L318-L328)). The losing claim is marked `CONTRADICTED` or `REFUTED`, and a `CONTRADICTION_DETECTED` research event is committed to SQLite.

### 5.4 Temporal State Reasoning
Implemented in [`src/argus/verifier/temporal_reasoner.py`](file:///data/shared/project/PlayGround/Argus/src/argus/verifier/temporal_reasoner.py):
- Supports `LifecycleState`: `OBSERVED`, `FILED`, `EFFECTIVE`, `AMENDED`, `RESTATED`, `SUPERSEDED`.
- Evaluates: *"What was true at time $T$?"* rather than *"What does the latest webpage say?"*
- Accurately resolves restatements (e.g. SEC 10-K superseded by a later 10-K/A amendment) and executive succession (e.g. Arthur Sterling succeeded by Emma Watson after a resignation date).

### 5.5 Knowledge Graph & Entity Resolution
- Entities are canonicalized via `EntityCanonicalizer` ([`src/argus/domain/canonicalizer.py`](file:///data/shared/project/PlayGround/Argus/src/argus/domain/canonicalizer.py)), which strips legal suffixes (`Inc.`, `LLC`, `GmbH`, `PLC`, `Holdings`) and computes normalized string matching.
- **Limitation**: Heimdallr does not use a persistent graph database (e.g. Neo4j). Relationships are stored as relational rows in SQLite (`argus.db`) and in-memory lists within `InvestigationState.relationships`.

---

## 6. AUTONOMY & AGENT CAPABILITIES

### 6.1 Objective Decomposition & Dynamic Planning
1. **Initial Task Decomposition**: Given an intelligence objective, `ResearchBrain` decomposes it into initial reconnaissance and domain tasks.
2. **Follow-Up & Disambiguation Tasks**: When the verifier discovers missing fields or flags a contradiction, it automatically calls `plan_followup_tasks` to schedule targeted queries.
3. **Personnel Fan-Out**: In [`src/argus/core/controller.py:179-201`](file:///data/shared/project/PlayGround/Argus/src/argus/core/controller.py#L179-L201), when the reconnaissance stage discovers physical manufacturing facilities, the controller dynamically fans out follow-up tasks specifically targeting facility plant managers and technical leads.

### 6.2 Stopping Policies & Resource Allocation
Heimdallr implements multi-criteria stopping:
- **Max Tasks / Step Limit**: Ceases execution when `tasks_executed >= objective.max_tasks`.
- **Diminishing Returns**: Stops when 3 consecutive tasks produce zero new supported claims ([`controller.py:132`](file:///data/shared/project/PlayGround/Argus/src/argus/core/controller.py#L132)).
- **Information Gain Policy**: In [`src/argus/investigation/stopping.py`](file:///data/shared/project/PlayGround/Argus/src/argus/investigation/stopping.py), `InvestigationStoppingPolicy` evaluates step gain ($\Delta \text{Gain} < 0.05$). If consecutive low-gain steps exceed the threshold or the target confidence exceeds 0.85, the investigation halts.

### 6.3 Crash Recovery & Persistence
Implemented in [`src/argus/investigation/store.py`](file:///data/shared/project/PlayGround/Argus/src/argus/investigation/store.py) (`InvestigationStore`):
- Saves atomic JSON snapshots of `InvestigationState` to disk (`storage/investigations/{id}/state.json`).
- `resume_investigation(investigation_id)` reloads state from disk, increments step budgets, and resumes the loop without losing accumulated claims or evidence.

### 6.4 Critical Autonomy Flaw: Hard-Coded Chaining Heuristics
While the architecture supports dynamic chaining, **the actual chaining logic in `InvestigationEngine._apply_observation` contains hard-coded heuristics tailored specifically to the benchmark evaluation**:
- [`src/argus/investigation/orchestrator.py:611`](file:///data/shared/project/PlayGround/Argus/src/argus/investigation/orchestrator.py#L611): Checks explicitly for `"Apex Technologies Europe Ltd"` or `"Apex Telemetry UK Limited"` to spawn an infrastructure question targeting `apex-telemetry.co.uk`.
- [`src/argus/investigation/orchestrator.py:633`](file:///data/shared/project/PlayGround/Argus/src/argus/investigation/orchestrator.py#L633): Checks explicitly for `"telemetry-cluster-01.apex-telemetry.co.uk"` and `"Rachel Thorne"` to spawn an identity question targeting `Cyberspace Defense Corp`.
- [`src/argus/investigation/orchestrator.py:686`](file:///data/shared/project/PlayGround/Argus/src/argus/investigation/orchestrator.py#L686): Hardcodes sanctions screening for `["Elena Rostova", "David Marcus", "Victor Kroll", "Apex Cyber Operations Ltd"]`.

**Verdict**: True generalized, domain-agnostic agentic chaining is **partially implemented**. On known benchmark scenarios, it behaves seamlessly; on completely arbitrary, un-modeled global entities, it falls back to basic keyword querying without deep specialist chaining.

---

## 7. RESTRICTIONS, POLICIES & SECURITY BOUNDARIES

### 7.1 Network & SSRF Defenses
Heimdallr possesses an enterprise-grade SSRF defense mechanism in [`src/argus/search/pipeline.py:95-150`](file:///data/shared/project/PlayGround/Argus/src/argus/search/pipeline.py#L95-L150):
1. **Disallowed Hosts**: Blocks `localhost`, `127.0.0.1`, `::1`, `169.254.169.254` (AWS/GCP metadata), and `metadata.google.internal`.
2. **Internal TLDs**: Rejects `.local`, `.internal`, `.localhost`, `.lan`, `.home`, `.corp`, `.arpa`.
3. **Direct IP Inspection**: Uses Python `ipaddress` to verify that IP literals are not private (`is_private`), loopback (`is_loopback`), link-local (`is_link_local`), or reserved.
4. **DNS Rebinding Protection**: Resolves domain names via `socket.getaddrinfo` before requesting and rejects hosts that resolve to non-global IP ranges.
5. **Browser-Level Enforcement**: Playwright routes abort requests to blocked URLs even if triggered by an HTTP redirect or embedded iframe ([`src/argus/crawler/fetcher.py:257-270`](file:///data/shared/project/PlayGround/Argus/src/argus/crawler/fetcher.py#L257-L270)).

### 7.2 Static AST Code Auditing
[`src/argus/competition/security_gate.py:37-86`](file:///data/shared/project/PlayGround/Argus/src/argus/competition/security_gate.py#L37-L86) implements `SecurityGateValidator.audit_candidate_source`:
- Parses candidate specialist Python code using `ast.parse`.
- Flags dangerous imports: `subprocess`, `shutil`, `socket`, `http.client`, `urllib.request`, `os.system`.
- Flags dangerous call nodes: `eval`, `exec`, `system`, `popen`, `spawn`, `__import__`.
- Blocks candidates that fail this static audit from being registered in the capability registry.

### 7.3 Adversarial Payload Sanitization & Defusing
In [`src/argus/competition/security_gate.py:88-170`](file:///data/shared/project/PlayGround/Argus/src/argus/competition/security_gate.py#L88-L170), raw untrusted text scraped from web pages or candidate observations passes through `sanitize_text`:
- Truncates oversized payloads (>2000 characters).
- Defuses instruction overrides:  
  `ignore previous instructions` $\rightarrow$ `[DEFUSED_INSTRUCTION_OVERRIDE]`
- Defuses prompt injection:  
  `you are now in debug mode` $\rightarrow$ `[DEFUSED_PROMPT_INJECTION]`
- Defuses command chaining:  
  `; rm -rf` $\rightarrow$ `; [DEFUSED_SHELL_COMMAND]`
- Defuses path traversal:  
  `../../etc/passwd` $\rightarrow$ `[DEFUSED_PATH_TRAVERSAL]/etc/[DEFUSED_FILE_PATH]`
- Defuses environment variable exfiltration:  
  `${OPENAI_KEY}` $\rightarrow$ `[DEFUSED_ENV_VAR]`
- Enforces unprivileged status: All candidate observations are explicitly tagged `clean["is_authoritative"] = False` ([line 215](file:///data/shared/project/PlayGround/Argus/src/argus/competition/security_gate.py#L215)).

---

## 8. INFRASTRUCTURE & SCALABILITY

### 8.1 Technology Stack & Dependencies

```
Python: >= 3.12
Runtime: Linux x86_64
Web Framework: FastAPI (API endpoints available, but engine runs primarily via CLI/SDK)
Async Framework: asyncio
Database: SQLite 3 via DatabaseManager (WAL mode enabled)
HTTP Client: HTTPX (AsyncClient)
Crawler Engine: Crawlee (RequestQueue, BasicCrawler)
Browser Automation: Playwright (Chromium headless)
HTML Parsing: BeautifulSoup4 (bs4)
Neural Decision Router: Laya (convaiinnovations/laya)
Deep Learning Framework: PyTorch (CPU wheel, 2.x)
Validation & Serialization: Pydantic v2
Search Providers: ddgs (DuckDuckGo search)
```

### 8.2 Database Architecture
- Implemented in [`src/argus/storage/db.py`](file:///data/shared/project/PlayGround/Argus/src/argus/storage/db.py) and [`src/argus/storage/repository.py`](file:///data/shared/project/PlayGround/Argus/src/argus/storage/repository.py).
- Tables: `objectives`, `tasks`, `documents`, `content_units`, `entities`, `claims`, `evidence`, `events`, `matrix_plant_leadership`.
- Database file defaults to `storage/argus.db` or `:memory:`.
- **Scaling Barrier**: SQLite is fundamentally a single-writer relational engine. When multi-worker crawling is attempted, write contention on `claims` and `events` produces database lock timeouts.

### 8.3 Concurrency & Scalability Limits
- **Execution Model**: Single machine, single process. No Celery, Celery-Beat, Redis, RabbitMQ, or Kafka queues exist in the codebase.
- **Memory Consumption**: Playwright Chromium browser instances consume 150–300 MB RAM per page. Concurrently rendering dozens of pages quickly saturates host RAM.
- **Throughput Profile**:
  - Offline In-Memory Eval V2: ~0.0033 seconds / task.
  - Live Web Crawling (Eval V1 Core): ~46.75 seconds / task (dominated by web latency, Playwright DOM rendering, and OpenRouter roundtrips).
- **Scale Ceiling**: In its current form, Heimdallr cannot scale beyond ~5–10 concurrent investigations on a single workstation without encountering SQLite locking and DuckDuckGo rate limiting.

---

## 9. EVALUATION & BENCHMARKS

The repository contains two completely distinct evaluation regimes that tell radically different stories about Heimdallr's capabilities.

### 9.1 Eval V2 Frozen Benchmark (120 Tasks) — Synthetic Testbed
- **Execution Location**: [`src/argus/evals/v2/runner.py`](file:///data/shared/project/PlayGround/Argus/src/argus/evals/v2/runner.py)
- **Task Dataset**: `data/evals/v2/benchmark_tasks.json` (120 tasks covering Corporate, Infrastructure, Identity, and Sanctions).
- **Ground Truth Isolation**: Fully enforced via `GroundTruthAccessGuard` and `TaskExecutionInput` DTO.
- **Measured Results**:

| Configuration | Pass Rate | Entity F1 | Field Accuracy | Evidence Correctness | Critical Fails | Runtime |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Argus Baseline (No Specialists)** | **`0.0%` (0/120)** | `20.3%` | `45.0%` | `99.2%` | 1 | 0.225s |
| **Identity Standalone** | **`12.5%` (15/120)** | `20.3%` | `16.7%` | `98.3%` | 2 | 0.052s |
| **Infrastructure Standalone** | **`12.5%` (15/120)** | `20.0%` | `18.8%` | `98.3%` | 2 | 0.080s |
| **Corporate Standalone** | **`12.5%` (15/120)** | `20.9%` | `24.6%` | `99.2%` | 1 | 0.167s |
| **Heimdallr V2 (Investigation Engine)** | **`100.0%` (120/120)** | **`99.9%`** | **`100.0%`** | **`100.0%`** | **0** | **0.394s** |

#### Why Did Heimdallr Score 100% on Eval V2?
1. **Pre-Curated Synthetic Corpus**: The benchmark queries [`CORPUS_V2_REGISTRY`](file:///data/shared/project/PlayGround/Argus/src/argus/evals/v2/corpus.py), an in-memory dictionary of synthetic SEC filings, UK Companies House filings, and WHOIS records created expressly for these 120 tasks.
2. **Hardcoded Extraction Heuristics**: As audited in Section 2, [`orchestrator.py:375-413`](file:///data/shared/project/PlayGround/Argus/src/argus/investigation/orchestrator.py#L375-L413) contains hardcoded regexes specifically matching the synthetic consortium vehicles and entities in this corpus.
3. **Audit Verdict**: The 100% score demonstrates internal code correctness, state machine stability, and graph resolution over clean, pre-structured documents. **It does NOT indicate 100% real-world intelligence capability.**

### 9.2 Eval V1 Historical Core Suite (11 Tasks) — Real Dirty-Web Reality
- **Dataset**: `data/evals/baseline_v1_core.json` (Real US automotive manufacturers: Ford, GM, Tesla, Stellantis, Rivian, Lucid).
- **Execution**: Live or VCR-recorded real web search, HTTP crawling, Playwright rendering, and actual worker/verifier execution.
- **Measured Results**:

| Metric | Measured Value | Analysis / Root Cause |
| :--- | :---: | :--- |
| **Task Pass Rate** | **`45.5%` (5 / 11 passed)** | Real-world noise, dynamic JS SPAs, and changing web structures cause 54.5% of tasks to fail. |
| **Field Accuracy** | **`50.0%`** | Half of the required operational fields (e.g. plant directors) were missed or incomplete. |
| **Entity Precision** | **`13.5%`** | **Severe extraction noise**: 86.5% of extracted entities were irrelevant background noise from web boilerplate. |
| **Entity Recall** | **`71.2%`** | Recovers the majority of mentioned entities, but cannot filter out the noise. |
| **Evidence Correctness**| **`92.5%`** | The Epistemic Verifier performs well: 92.5% of committed claims are strictly grounded. |
| **Unsupported Claim Rate**| **`7.5%`** | Low hallucination rate thanks to token alignment checks. |
| **Contradiction Detection**| **`90.9%`** | High effectiveness at catching conflicting information between web sources. |
| **Task Latency** | **`46.75s / task`** | 514.2s total run time (~8.5 minutes across 11 tasks). |

---

## 10. CURRENT CAPABILITY MATRIX

| Capability | Status | Evidence (Code Path) | Verified Limitations | Confidence |
| :--- | :---: | :--- | :--- | :---: |
| **Live Web Search** | **IMPLEMENTED** | [`src/argus/search/duckduckgo.py`](file:///data/shared/project/PlayGround/Argus/src/argus/search/duckduckgo.py) | Rate-limited to 2 concurrent queries; relies on unauthenticated scrapers. | HIGH |
| **SSRF Protection** | **IMPLEMENTED** | [`src/argus/search/pipeline.py:95`](file:///data/shared/project/PlayGround/Argus/src/argus/search/pipeline.py#L95) | Excellent; blocks loopback, private IPs, metadata endpoints, DNS rebinding. | HIGH |
| **Two-Tier Crawling** | **IMPLEMENTED** | [`src/argus/crawler/fetcher.py`](file:///data/shared/project/PlayGround/Argus/src/argus/crawler/fetcher.py) | 5MB response ceiling; Playwright browser overhead limits concurrency. | HIGH |
| **HTML Table Extraction**| **IMPLEMENTED** | [`src/argus/crawler/extractor.py:129`](file:///data/shared/project/PlayGround/Argus/src/argus/crawler/extractor.py#L129)| Formats HTML tables into clean Markdown tables for LLM consumption. | HIGH |
| **Neural Snippet Triage**| **IMPLEMENTED** | [`src/argus/brain/system1.py`](file:///data/shared/project/PlayGround/Argus/src/argus/brain/system1.py) | Laya System 1 filters ~80% irrelevant search snippets in ~33ms. | HIGH |
| **Epistemic Verification**| **IMPLEMENTED** | [`src/argus/verifier/engine.py`](file:///data/shared/project/PlayGround/Argus/src/argus/verifier/engine.py) | Enforces passage grounding; prevents inferred claims from becoming facts. | HIGH |
| **Syndication Clustering**| **IMPLEMENTED** | [`src/argus/verifier/syndication_intelligence.py`](file:///data/shared/project/PlayGround/Argus/src/argus/verifier/syndication_intelligence.py)| Clusters news wire duplicates by domain and content hash. | HIGH |
| **Temporal Reasoning** | **IMPLEMENTED** | [`src/argus/verifier/temporal_reasoner.py`](file:///data/shared/project/PlayGround/Argus/src/argus/verifier/temporal_reasoner.py)| Evaluates legal/operational state at time $T$; models amendments and resignations. | HIGH |
| **Prompt Injection Defense**| **IMPLEMENTED**| [`src/argus/competition/security_gate.py:88`](file:///data/shared/project/PlayGround/Argus/src/argus/competition/security_gate.py#L88)| Regex defusing neutralizes instruction overrides, path traversals, shell commands.| HIGH |
| **Investigation Persistence**| **IMPLEMENTED**| [`src/argus/investigation/store.py`](file:///data/shared/project/PlayGround/Argus/src/argus/investigation/store.py) | Atomic disk snapshots allow full crash recovery and resumption. | HIGH |
| **Corporate Specialist** | **PARTIAL** | [`src/argus/specialists/corporate/`](file:///data/shared/project/PlayGround/Argus/src/argus/specialists/corporate/) | Parses SEC/UK filing schemas, but lacks live direct EDGAR/Companies House API client. | HIGH |
| **LinkedIn Profiling** | **PARTIAL** | [`src/argus/search/linkedin.py`](file:///data/shared/project/PlayGround/Argus/src/argus/search/linkedin.py) | SERP dorking only; cannot traverse authenticated LinkedIn graphs. | HIGH |
| **4chan OSINT** | **PARTIAL** | [`src/argus/search/fourchan.py`](file:///data/shared/project/PlayGround/Argus/src/argus/search/fourchan.py) | Real API integration, but restricted to `/o/` and `/biz/` boards. | HIGH |
| **Multi-Specialist Chaining**| **PARTIAL** | [`src/argus/investigation/orchestrator.py:609`](file:///data/shared/project/PlayGround/Argus/src/argus/investigation/orchestrator.py#L609)| Chaining logic contains hardcoded regexes matching benchmark entities. | HIGH |
| **Sanctions & PEP Screening**| **EXPERIMENTAL**| [`src/argus/specialists/sanctions/`](file:///data/shared/project/PlayGround/Argus/src/argus/specialists/sanctions/) | In-memory lookup over 137-line static dictionary; no live yente/OpenSanctions API. | HIGH |
| **Dark Web / Onion OSINT** | **EXPERIMENTAL**| [`src/argus/specialists/onion/`](file:///data/shared/project/PlayGround/Argus/src/argus/specialists/onion/) | In-memory lookup over mock dictionary; no Tor SOCKS5 proxy or circuit code. | HIGH |
| **Handle Discovery (Blackbird)**| **EXPERIMENTAL**| [`src/argus/specialists/blackbird_specialist.py`](file:///data/shared/project/PlayGround/Argus/src/argus/specialists/blackbird_specialist.py)| Emulates probe architecture over mock data; hardcodes execution metrics. | HIGH |
| **PDF Document Parsing** | **MISSING** | *None* | Zero PDF libraries in dependencies; binary PDFs discarded as unreadable. | HIGH |
| **Local LLM Inference** | **MISSING** | *None* | No vLLM, Ollama, or llama.cpp runtimes; relies entirely on OpenRouter API. | HIGH |
| **Distributed Queueing** | **MISSING** | *None* | No Celery, Redis, or Kafka; single-process asyncio architecture. | HIGH |
| **JEV Decision Engine** | **MISSING** | *None* | Completely absent from repository (0 occurrences). | HIGH |

---

## 11. READINESS FOR A SOVEREIGN INTELLIGENCE PLATFORM

### A. General-Purpose Global OSINT
- **Current State**: Operates as a focused web scraper and search orchestrator. Effective for targeted corporate lookups where sources publish plain HTML.
- **Missing Prerequisites**: Robust anti-bot evasion (residential proxies, CAPTCHA bypass); full multi-modal document extraction (PDF, DOCX); real-time social platform APIs (X/Twitter, Telegram, VK, Reddit).
- **Major Technical Risks**: Search engine rate-limiting and IP banning completely paralyze unauthenticated discovery within minutes of sustained global scanning.
- **Readiness Rating**: **POOR (2/10)**.

### B. Multilingual Geopolitical Research
- **Current State**: Relies on DeepSeek's internal multilingual capabilities and Laya's language coverage.
- **Missing Prerequisites**: Native non-Latin entity extraction (Cyrillic, Arabic, Hanzi); localized search dork formulation; regional search engine adapters (Yandex, Baidu).
- **Major Technical Risks**: Severe blind spots in non-English jurisdictions; high hallucination and false-negative rates when mapping foreign corporate registries.
- **Readiness Rating**: **VERY POOR (1/10)**.

### C. Corporate and Industrial Intelligence
- **Current State**: **This is Heimdallr's strongest operational domain.** Successfully profiles companies, maps assembly plants, identifies executives, and verifies corporate leadership against SEC disclosures.
- **Missing Prerequisites**: Direct SEC EDGAR EFTS API ingestion; UK Companies House API integration; live international corporate registry connectors (BVD Orbis, OpenCorporates).
- **Major Technical Risks**: When official filings are provided exclusively as PDF attachments, the system fails to extract any data.
- **Readiness Rating**: **MODERATE (5/10)**.

### D. Large-Scale Evidence-Backed Investigations
- **Current State**: Epistemic Verifier and Syndication Intelligence are exceptionally well-engineered to enforce provenance and prevent duplicate source counting.
- **Missing Prerequisites**: High-throughput distributed crawler workers; scalable vector / hybrid search over millions of crawled pages; graph database integration.
- **Major Technical Risks**: Database lock contention in SQLite and memory exhaustion from Playwright will cause crashes on investigations exceeding ~100 sources.
- **Readiness Rating**: **POOR (3/10)**.

### E. Persistent Intelligence Knowledge Systems
- **Current State**: SQLite repository stores entities, claims, and evidence. `InvestigationStore` provides atomic JSON snapshots.
- **Missing Prerequisites**: Knowledge graph database (e.g. Neo4j, Memgraph); cross-investigation entity disambiguation; ontologies beyond basic automotive and corporate schemas.
- **Major Technical Risks**: Re-running investigations currently purges or overwrites matrices ([`controller.py:85`](file:///data/shared/project/PlayGround/Argus/src/argus/core/controller.py#L85)) rather than incrementally updating an enterprise knowledge graph.
- **Readiness Rating**: **POOR (3/10)**.

### F. Secure Government and Enterprise Deployments
- **Current State**: Outstanding network safety (SSRF guard, loopback blocking, DNS rebinding prevention) and AST security gating.
- **Missing Prerequisites**: Air-gapped local LLM inference; role-based access control (RBAC); cryptographic audit trail signatures; secret vault integrations.
- **Major Technical Risks**: **Exfiltration of Classified / Proprietary Intelligence via Remote LLM**: All investigated text snippets and entities are transmitted over the public internet to the OpenRouter API (`https://openrouter.ai/api/v1`).
- **Readiness Rating**: **CRITICAL RISK / UNUSABLE IN SOVEREIGN ENVIRONMENTS (1/10)**.

### G. Integration with Authorized Private Data Sources
- **Current State**: No enterprise data connectors exist.
- **Missing Prerequisites**: Connectors for S3, Azure Blob, SharePoint, ElasticSearch, internal SQL databases, or internal document repositories.
- **Major Technical Risks**: System assumes all inputs originate from HTTP URLs or in-memory fixtures.
- **Readiness Rating**: **NON-EXISTENT (0/10)**.

### H. Long-Running Autonomous Intelligence Workflows
- **Current State**: Basic task state machine (`READY` -> `RUNNING` -> `COMPLETED`/`FAILED`) and crash recovery snapshotting.
- **Missing Prerequisites**: Persistent worker daemon processes; background scheduler; human-in-the-loop review queues; dynamic budget allocation across multi-week runs.
- **Major Technical Risks**: Investigations run inside active Python processes. If the process is terminated, resumption requires manual CLI invocation.
- **Readiness Rating**: **POOR (2/10)**.

---

## 12. FINAL TECHNICAL ASSESSMENT

### Direct Answers to the 10 Audit Questions

#### 1. What can Heimdallr V3 reliably accomplish TODAY?
Heimdallr can autonomously take a corporate research target, formulate search queries, scrape candidate web pages using HTTPX and Playwright, filter noise using Laya System 1, extract leadership and facility claims, and verify them against strict epistemic grounding standards in an SQLite database. It reliably prevents SSRF attacks, filters out syndicated news duplicates, and defuses adversarial prompt injections.

#### 2. What does its architecture theoretically support but not yet demonstrate?
The architecture theoretically supports autonomous, multi-hop investigation across corporate, infrastructure, identity, and sanctions specialists. However, it only demonstrates this today within an in-memory synthetic fixture corpus (`CORPUS_V2_REGISTRY`). On the open, live web, it has only demonstrated automotive corporate intelligence.

#### 3. What are its 10 most significant verified limitations?
1. **Zero PDF / Document Parsing**: Cannot read binary PDF files; completely ignores regulatory filings, whitepapers, and reports published as PDFs.
2. **Synthetic Specialist Mocking**: Dark-Web/Onion, Sanctions, and Handle specialists operate on static Python dictionaries rather than live network services.
3. **Hardcoded Benchmark Routing**: Multi-specialist chaining in `orchestrator.py` contains hardcoded entity regexes written specifically to pass the 120-task benchmark.
4. **No Local LLM Runtime**: Entirely dependent on the remote OpenRouter API (`deepseek/deepseek-chat`), violating sovereign air-gap mandates.
5. **Absence of JEV**: The heavily discussed "JEV" decision provider does not exist anywhere in the codebase.
6. **Severe Live-Web Extraction Noise**: On dirty web data (Eval V1 Core), entity precision drops to 13.5% (86.5% of extracted entities are irrelevant noise).
7. **Single-Process Asyncio Bottleneck**: Lacks distributed queues (Celery/Redis); single-threaded outer loop serializes task execution.
8. **SQLite Storage Contention**: Relies on a single local SQLite file, creating write-lock bottlenecks during multi-source investigations.
9. **No Native Multilingual Processing**: Lacks foreign-language tokenization, translation pipelines, or regional search adapters (Yandex, Baidu).
10. **Brittle Discovery Scrapers**: Relies on unauthenticated DuckDuckGo scrapers that rapidly rate-limit and block sustained investigation traffic.

#### 4. Which limitations are fundamental architectural problems?
- The **single-process execution model** and **SQLite single-writer lock**: Scaling to large intelligence investigations requires a distributed microservices architecture (task queues, separate ingestion workers, graph store).
- The **hardcoded regex chaining** in [`orchestrator.py`](file:///data/shared/project/PlayGround/Argus/src/argus/investigation/orchestrator.py#L375-L413): Chaining must be driven by an ontological reasoning engine or LLM plan refinement, not static string matching.

#### 5. Which limitations are caused by infrastructure, budgets, or providers?
- **Unauthenticated Search Rate Limits**: DuckDuckGo's concurrency cap of 2 and 429 errors are caused by lack of enterprise search API keys (e.g. Brave Search API, Bing Web Search API, or Google Custom Search API).
- **External Model Latency**: 2–5 second delays per LLM call stem from remote OpenRouter HTTP calls rather than an on-premise GPU cluster running vLLM.

#### 6. Which limitations are caused by prompts, policies, or access controls?
- **Entity Noise (13.5% Precision)**: Caused by prompt templates in [`src/argus/worker/prompts.py`](file:///data/shared/project/PlayGround/Argus/src/argus/worker/prompts.py) that instruct the model to extract all entities broadly rather than strictly filtering for in-scope target entities.
- **LinkedIn Authwall Limitation**: A deliberate policy of avoiding authenticated scraping to prevent account suspension, falling back to SERP dorking.

#### 7. Which components are strongest and should be preserved?
1. **Epistemic Verifier Engine** ([`src/argus/verifier/engine.py`](file:///data/shared/project/PlayGround/Argus/src/argus/verifier/engine.py)): World-class implementation of claim-evidence grounding and contradiction adjudication.
2. **Syndication Intelligence** ([`src/argus/verifier/syndication_intelligence.py`](file:///data/shared/project/PlayGround/Argus/src/argus/verifier/syndication_intelligence.py)): Essential OSINT feature preventing wire-service duplicate corroboration.
3. **SSRF Guard & Route Interceptor** ([`src/argus/search/pipeline.py`](file:///data/shared/project/PlayGround/Argus/src/argus/search/pipeline.py) & [`fetcher.py`](file:///data/shared/project/PlayGround/Argus/src/argus/crawler/fetcher.py)): Robust network security implementation.
4. **Two-Tier Fetcher Architecture** ([`src/argus/crawler/fetcher.py`](file:///data/shared/project/PlayGround/Argus/src/argus/crawler/fetcher.py)): Elegant balance of fast HTTP streaming and Playwright browser escalation.
5. **System 1 Triage Router (Laya)** ([`src/argus/brain/system1.py`](file:///data/shared/project/PlayGround/Argus/src/argus/brain/system1.py)): Outstanding cost-saving filter (~33ms) for candidate pruning.

#### 8. Which components are weakest or insufficiently validated?
1. **Investigation Orchestrator** ([`src/argus/investigation/orchestrator.py`](file:///data/shared/project/PlayGround/Argus/src/argus/investigation/orchestrator.py)): Compromised by hardcoded benchmark regexes; insufficiently validated on live open-web data.
2. **Onion Specialist** ([`src/argus/specialists/onion/`](file:///data/shared/project/PlayGround/Argus/src/argus/specialists/onion/)): Completely emulated in-memory; zero real Tor protocol code.
3. **Sanctions Specialist** ([`src/argus/specialists/sanctions/`](file:///data/shared/project/PlayGround/Argus/src/argus/specialists/sanctions/)): Static 137-line dictionary; lacks real yente/OpenSanctions API integration.
4. **Document Extractor** ([`src/argus/crawler/extractor.py`](file:///data/shared/project/PlayGround/Argus/src/argus/crawler/extractor.py)): Completely blind to PDF documents.

#### 9. What evidence is missing to assess production readiness?
- Zero benchmarks evaluate the system against a dirty, uncurated corpus of 10,000+ real-world documents.
- Zero stress tests measuring SQLite behavior under high concurrency.
- Zero empirical benchmarks measuring performance with fully local, air-gapped LLMs.
- Zero metrics on long-running memory stability of Playwright under 24/7 continuous crawling.

#### 10. How far is Heimdallr V3 from a credible general-purpose intelligence research engine?
**Heimdallr V3 is approximately 12–18 months of disciplined engineering away from a credible sovereign intelligence platform.**

It is not a "toy" — its verifier invariants, syndication intelligence, and two-tier crawler represent high-caliber systems engineering. However, it currently suffers from an architectural split personality: its robust live engine is trapped in a narrow automotive corporate domain, while its multi-specialist investigation framework is largely an in-memory simulation hardcoded to pass a synthetic 120-task benchmark.

To become a true sovereign intelligence platform, the team must:
1. Strip out hardcoded benchmark regexes in favor of generalized ontological chaining.
2. Add production PDF and document parsing (`pdfplumber` / OCR).
3. Connect specialists to real data providers (live Tor SOCKS5 daemons, self-hosted Yente/OpenSanctions instances, authenticated corporate registries).
4. Replace SQLite and single-process `asyncio` with a distributed task queue (Celery/Redis) and graph database (Neo4j).
5. Implement local vLLM inference to satisfy true sovereign air-gap security requirements.

---

*Report certified by the Independent Verification & Technical Audit Team.*  
*Artifacts verified against commit `56c62b5008219f558c89a79c34cd1bf5ec0f4d79`.*
