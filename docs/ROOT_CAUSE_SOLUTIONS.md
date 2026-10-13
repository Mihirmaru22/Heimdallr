# Engineering Solutions Architecture: Resolving Intelligence Gaps in Argus

> **Document Version:** 1.0.0  
> **Status:** Approved Architecture & Implementation Blueprint  
> **Target Problem:** Resolution of Missing Plant Heads, Tech Leads, and Contact Information  
> **Reference Analysis:** [`root_cause_analysis.md`](file:///home/mihir/.gemini/antigravity-ide/brain/cc3d0eb5-763b-409c-9eab-3d2ba27d8a84/root_cause_analysis.md)

---

## Executive Summary

The forensic root cause audit of the initial Argus run revealed that **zero plant heads, zero tech leads, and zero contact details** were extracted because of an interconnected failure chain spanning six layers:
1. **Search Layer:** A static search provider that ignored dynamic queries and returned only 6 Wikipedia URLs.
2. **Scheduling Layer:** A rigid `max_tasks=2` ceiling that aborted the engine after reconnaissance, stranding 9 targeted tasks in `READY` status.
3. **Crawl Layer:** A `max_crawl_pages_per_task=1` bottleneck that discarded all search results beyond the first URL.
4. **Source Layer:** Sourcing solely from Wikipedia, which by policy omits personal contact details, operational plant managers, and engineering directors.
5. **Epistemic Gate Layer:** A stopping criteria logic error where budget checks short-circuited before epistemic checks and falsely reported `coverage_score=1.0` and `missing_fields=[]`.
6. **Ontology & Extraction Layer:** A substring mismatch between required field names (`plant_head`, `tech_lead`) and worker claim predicates (`HAS_LEADERSHIP`), preventing the planner from recognizing discovered facts.

This document specifies the concrete, production-ready solutions for each failure layer.

```mermaid
flowchart TD
    subgraph Layer 1: Search & Discovery
        DDG["DuckDuckGo API / ddgs"] --> Casc["Search Cascade & Dorking Engine"]
        Casc --> Queries["Targeted Leadership & News Queries"]
    end

    subgraph Layer 2: Crawl & Ingestion
        Queries --> Ranker["Pre-Crawl Relevance Ranker"]
        Ranker --> Fetcher["Adaptive Fetcher (3-5 pages/task + JS fallback)"]
    end

    subgraph Layer 3: Epistemic Extraction
        Fetcher --> Worker["Worker with Leadership & Contact Ontology"]
        Worker --> Verifier["Expert Verifier (Cross-Source Adjudication)"]
    end

    subgraph Layer 4: Brain & Epistemic Feedback
        Verifier --> Claims["Supported Claims in DB"]
        Claims --> EpistemicGate["Semantic Predicate Evaluator"]
        EpistemicGate --> PhaseCtrl["Multi-Phase Staged Controller"]
        PhaseCtrl -->|Unsatisfied Fields| Followup["Followup Child Tasks"]
        Followup --> Casc
    end

    style Casc fill:#2563EB,color:#fff
    style Worker fill:#059669,color:#fff
    style EpistemicGate fill:#7C3AED,color:#fff
    style PhaseCtrl fill:#D97706,color:#fff
```

---

## Root Cause 1: Search Provider & Source Space Limitation

### Problem Recap
[`AutomotiveSearchProvider`](file:///data/shared/project/PlayGround/Argus/scripts/run_us_automotive_category1.py#L28-L87) was a static mock with 6 hardcoded Wikipedia URLs. When the Brain planner generated targeted queries like `"Ford Kentucky Truck Plant plant manager"`, the provider pattern-matched `"ford"` and returned Wikipedia articles about Ford factories, completely ignoring the leadership search intent.

---

### Solution 1.1: Live Multi-Engine Search Pipeline with Cascade & Fallback

Implement a resilient, multi-backend search architecture that queries the open web and automatically falls back if rate-limited or blocked:

```mermaid
flowchart LR
    Q["Search Query"] --> Primary{"Primary: DuckDuckGo"}
    Primary -->|Success| Results["Normalized Search Results"]
    Primary -->|Rate Limit / Error| Secondary{"Secondary: SearXNG / Brave"}
    Secondary -->|Success| Results
    Secondary -->|Error| Tertiary{"Tertiary: Google Custom / SerpAPI"}
    Tertiary -->|Success| Results
    Tertiary -->|All Failed| Cache["Cached Search Store"]
```

#### Architecture Specification: `SearchCascadeProvider`
- **Primary Backend:** DuckDuckGo (`ddgs` library) — 100% free, zero API key required, supports localized search and site dorking.
- **Secondary Backend:** Self-hosted SearXNG instance or Brave Search API — open web indexing, privacy-respecting, high rate limits.
- **Tertiary Backend:** SerpAPI / Google Custom Search Engine (CSE) — gold standard for business directories and news articles.
- **Circuit Breaker & Backoff:** Exponential backoff with random jitter (1.5s to 4.0s) and automatic provider failover upon HTTP 429 or empty response arrays.

```python
class SearchCascadeProvider(SearchProvider):
    """Resilient search provider chaining multiple search backends."""

    def __init__(self, providers: list[SearchProvider], timeout: float = 15.0):
        self.providers = providers
        self.timeout = timeout

    async def search(self, query: SearchQuery) -> SearchResponse:
        last_error = None
        for provider in self.providers:
            try:
                resp = await provider.search(query)
                if resp.results:
                    return resp
            except Exception as exc:
                last_error = exc
                continue
        if last_error:
            raise SearchProviderError(f"All cascade search backends failed: {last_error}")
        return SearchResponse(query=query.query_text, results=[])
```

---

### Solution 1.2: Intelligence-Targeted Search Dorking Engine

The Brain must not generate generic keyword queries. It must generate **intelligence dorks** tailored to executive, plant-level, and operational personnel discovery:

| Intelligence Target | Search Dork Pattern | Target Information Discovered |
| :--- | :--- | :--- |
| **Plant Manager / Head** | `"[Plant Name]" ("plant manager" OR "plant director" OR "site lead" OR "general manager")` | Official appointments, press releases, regional business journal profiles |
| **Technical / Engineering Lead** | `"[Plant Name]" ("chief engineer" OR "lead engineer" OR "technical director" OR "engineering manager")` | Technical press announcements, patent filings, conference presentations |
| **LinkedIn Professional Search** | `site:linkedin.com/in "[Company]" "[Plant Name]" ("Plant Manager" OR "Operations Director")` | Confirmed current job titles, tenure dates, location verification |
| **Corporate Newsrooms** | `site:media.[company].com OR site:press.[company].com "[Plant Name]" ("named" OR "appointed" OR "promoted")` | Unimpeachable primary corporate evidence of leadership |
| **Local Business Press** | `("Crain's Detroit Business" OR "Louisville Business First" OR "Detroit Free Press") "[Plant Name]" "manager"` | Detailed local operational reporting often missed by national press |
| **Regulatory & Safety Filings** | `site:osha.gov OR site:epa.gov/enviro "[Plant Name]" ("establishment" OR "contact")` | Public record compliance contacts, site directors, plant environmental engineers |

---

## Root Cause 2: Arbitrary Task Budgeting & Pipeline Starvation

### Problem Recap
In the original script, `max_tasks=2` was hardcoded. The Brain planned 11 tasks, but after completing Task #1 (Company Reconnaissance) and Task #2 (Factory Identification), the engine terminated immediately, leaving tasks for plant managers, tech leads, and contact information permanently unexecuted.

---

### Solution 2.1: Dynamic Formula-Driven Budget Allocation

Instead of arbitrary static numbers, calculate `max_tasks` dynamically based on the breadth of the objective target:

$$\text{Task Budget} = T_{\text{recon}} + \sum_{m \in \text{Manufacturers}} \left( T_{\text{facilities}}(m) + N_{\text{plants}}(m) \times T_{\text{leadership}} \right) + T_{\text{synthesis}}$$

Where:
- $T_{\text{recon}} = 2$ (high-level industry reconnaissance)
- $T_{\text{facilities}}(m) = 1$ task per major automaker
- $T_{\text{leadership}} = 2$ tasks per identified facility (1 for Plant Head / Tech Lead, 1 for Contact & Verification)
- $T_{\text{synthesis}} = 2$ (deduplication, cross-validation, and dossier generation)

For a targeted investigation of the Big Three (GM, Ford, Stellantis) with 5 major assembly plants:
$$\text{Budget} = 2 + (3 \times 1) + (5 \times 2) + 2 = \mathbf{17 \text{ tasks}}$$

---

### Solution 2.2: Staged Multi-Phase Execution Pipeline

Replace the monolithic loop in [`ArgusController.run()`](file:///data/shared/project/PlayGround/Argus/src/argus/core/controller.py#L75) with a **5-Phase Pipeline Architecture**:

```mermaid
stateDiagram-v2
    [*] --> Phase1_Reconnaissance
    Phase1_Reconnaissance --> Phase2_FacilityMapping: Companies Identified
    Phase2_FacilityMapping --> Phase3_LeadershipDiscovery: Facilities Grounded
    Phase3_LeadershipDiscovery --> Phase4_ContactResolution: Names & Roles Grounded
    Phase4_ContactResolution --> Phase5_EpistemicSynthesis: Evidence Verified
    Phase5_EpistemicSynthesis --> [*]: Dossier Generated
```

1. **Phase 1: Industry Reconnaissance (Budget: 2–3 tasks)**
   - Target: Discover active US manufacturers and operational brands.
   - Exit Criteria: At least $N$ validated automotive manufacturing entities.
2. **Phase 2: Manufacturing Facility Mapping (Budget: 3–5 tasks)**
   - Target: Enumerate assembly plants, powertrain plants, stamping facilities per automaker.
   - Exit Criteria: Facility entities linked via `OPERATES_FACILITY` to parent automakers.
3. **Phase 3: Operational Leadership Discovery (Budget: 1–2 tasks per plant)**
   - Target: Identify Plant Manager / Site Director and Chief Plant Engineer.
   - Sourcing: Corporate press releases, local news, and LinkedIn public profiles.
4. **Phase 4: Contact & Verification Resolution (Budget: 1 task per plant)**
   - Target: Extract official email addresses, facility phone numbers, LinkedIn URLs.
   - Sourcing: Company directories, corporate press releases, regional chambers of commerce.
5. **Phase 5: Cross-Validation & Epistemic Synthesis (Budget: 1–2 tasks)**
   - Target: Reconcile contradictions, ensure active tenure (not retired/promoted), produce dossier.

---

### Solution 2.3: Checkpoint, Pause, and Interactive Budget Resumption

Modify [`ArgusController`](file:///data/shared/project/PlayGround/Argus/src/argus/core/controller.py) to support incremental resumption:
- Save execution state (completed tasks, pending tasks, discovered entities, claims) to SQLite after every task.
- Provide a `resume_investigation(objective_id, additional_tasks=10)` method so investigations can be expanded without re-running completed reconnaissance.

---

## Root Cause 3: Crawl Breadth & Fetching Bottleneck

### Problem Recap
[`run_us_automotive_category1.py:152`](file:///data/shared/project/PlayGround/Argus/scripts/run_us_automotive_category1.py#L152) invoked `controller.run(objective, max_crawl_pages_per_task=1)`. The loop in [`controller.py:136`](file:///data/shared/project/PlayGround/Argus/src/argus/core/controller.py#L136) clipped discovered URLs to `[:1]`. Even when DuckDuckGo returned 8 high-quality URLs, only the first was fetched, discarding 87% of potential evidence.

---

### Solution 3.1: Adaptive Crawl Quotas per Task Type

Different tasks require different crawl depths:

| Task Type | Recommended Quota | Rationale |
| :--- | :---: | :--- |
| **High-Level Reconnaissance** | 2–3 pages | Broad overviews (Wikipedia, Trade Association directories) |
| **Facility Identification** | 3–4 pages | Plant lists across corporate investor & operations pages |
| **Leadership Identification** | 4–6 pages | News articles, press releases, regional business profiles |
| **Contact Info Verification** | 3–5 pages | Company contact directories, press kits, official notices |

---

### Solution 3.2: Pre-Crawl Relevance Ranking (`ScoredURLRanker`)

Do not simply fetch the first $N$ URLs returned by search. Score each URL prior to crawling based on domain authority, snippet content, and target entity mentions:

```python
class ScoredURLRanker:
    """Ranks search result URLs before fetching to maximize information yield."""

    HIGH_VALUE_DOMAINS = {
        "media.ford.com": 3.0,
        "pressroom.gm.com": 3.0,
        "media.stellantisnorthamerica.com": 3.0,
        "autonews.com": 2.5,
        "crainsdetroit.com": 2.5,
        "linkedin.com": 2.0,
        "osha.gov": 2.0,
    }

    LEADERSHIP_KEYWORDS = {
        "plant manager", "plant director", "site lead",
        "chief engineer", "operations manager", "general manager",
    }

    def score(self, item: SearchResult, task: ResearchTask) -> float:
        score = 1.0
        # 1. Domain authority bonus
        for domain, weight in self.HIGH_VALUE_DOMAINS.items():
            if domain in item.url.lower():
                score *= weight
        # 2. Snippet keyword match bonus
        snippet_lower = (item.title + " " + item.snippet).lower()
        for kw in self.LEADERSHIP_KEYWORDS:
            if kw in snippet_lower:
                score += 1.5
        # 3. Penalize low-yield domains (forums, general encyclopedias if searching leadership)
        if "wikipedia.org" in item.url.lower() and "leadership" in task.title.lower():
            score *= 0.1
        return score
```

---

### Solution 3.3: Two-Tier Fetcher with Headless Playwright Fallback

Many modern corporate newsrooms (e.g., GM Pressroom, Stellantis Media) and company directory portals rely on client-side React/Vue rendering. 
- **Tier 1 (Fast):** `httpx` async HTTP GET (handles 85% of static content in <300ms).
- **Tier 2 (Headless):** If HTTP status is 200 but extracted text content is < 200 words or contains `<div id="root"></div>`, dispatch to Playwright headless Chromium to execute JavaScript, await DOM hydration, and extract the complete text.

---

## Root Cause 4: Intelligence Domain & Content Mismatch

### Problem Recap
Wikipedia was the only source used. Wikipedia policy (WP:BLP, WP:NOTDIRECTORY) prohibits phone numbers, email addresses, and exhaustive directories of plant-level operational personnel.

---

### Solution 4.1: Five-Tier Sourcing Matrix

Argus must systematically ingest documents from five distinct source archetypes:

```
┌───────────────────────────────────────────────────────────────────────────┐
│                     ARGUS 5-TIER INTELLIGENCE MATRIX                      │
│                                                                           │
│  [Tier 1] Corporate Media & Press Releases (Primary Ground Truth)         │
│           • media.ford.com, pressroom.gm.com, media.stellantis.com         │
│           • Content: "Ford names John Smith Plant Manager at Kentucky..."  │
│                                                                           │
│  [Tier 2] Regulatory & Compliance Filings (High Reliability)             │
│           • OSHA inspection reports, EPA facility air/water permits       │
│           • Content: Facility address, designated site director/contact   │
│                                                                           │
│  [Tier 3] Local & Regional Business Press (High Specificity)              │
│           • Crain's Detroit Business, Louisville Business First            │
│           • Content: In-depth interviews with plant managers, tech heads  │
│                                                                           │
│  [Tier 4] Industry Trade Publications & Directories (Broad Coverage)      │
│           • Automotive News, IndustryWeek, Assembly Magazine, ThomasNet   │
│           • Content: Plant profiles, plant rankings, production heads    │
│                                                                           │
│  [Tier 5] Public Professional Profiles & Snippets (Verification)          │
│           • LinkedIn public snippets, ZoomInfo public company profiles    │
│           • Content: Current job title, active tenure dates               │
└───────────────────────────────────────────────────────────────────────────┘
```

---

### Solution 4.2: Domain-Specific Query Templates

Equip `ResearchBrain` with template-driven query generation for automotive facilities:

```python
AUTOMOTIVE_QUERY_TEMPLATES = {
    "plant_head": [
        '"{company}" "{plant_name}" ("plant manager" OR "plant director" OR "site manager")',
        'site:linkedin.com/in "{company}" "{plant_name}" "Plant Manager"',
        'site:media.{company_domain} "{plant_name}" ("manager" OR "appointed" OR "director")',
        '"{plant_name}" "plant manager" ("announced" OR "joined" OR "named")',
    ],
    "tech_lead": [
        '"{company}" "{plant_name}" ("chief engineer" OR "lead engineer" OR "technical director")',
        'site:linkedin.com/in "{company}" "{plant_name}" ("Engineering Manager" OR "Chief Engineer")',
        '"{plant_name}" ("advanced manufacturing engineer" OR "technical lead")',
    ],
    "contact_info": [
        '"{company}" "{plant_name}" ("phone" OR "address" OR "contact" OR "media contact")',
        'site:media.{company_domain} "{plant_name}" contact press',
        '"{plant_name}" ("office:" OR "phone:" OR "email:")',
    ],
}
```

---

## Root Cause 5: Epistemic Gate vs. Budget Check Priority Inversion

### Problem Recap
In [`planner.py:99-106`](file:///data/shared/project/PlayGround/Argus/src/argus/brain/planner.py#L99-L106):
```python
if tasks_executed >= objective.max_tasks:
    return StoppingEvaluation(
        should_stop=True,
        reason=f"Task execution budget reached ({tasks_executed}/{objective.max_tasks}).",
        missing_fields=[],      # BUG: Falsely reports no missing fields!
        coverage_score=1.0,     # BUG: Falsely reports 100% coverage!
    )
```
1. **False Coverage:** When budget was reached, the method returned `coverage_score=1.0` and `missing_fields=[]`, masking the fact that 0% of leadership data had been found.
2. **Priority Inversion:** The budget check ran before epistemic evaluation, preventing the controller from recognizing that high-priority fields were missing.

---

### Solution 5.1: Epistemic-First Stopping Evaluator

Refactor [`evaluate_stopping_criteria`](file:///data/shared/project/PlayGround/Argus/src/argus/brain/planner.py#L93) to calculate true epistemic coverage first, regardless of task budget:

```python
def evaluate_stopping_criteria(
    self,
    objective: ResearchObjective,
    tasks_executed: int,
) -> StoppingEvaluation:
    """Evaluate research status based on epistemic completeness and budget safety."""
    # 1. Epistemic requirement satisfaction (ALWAYS compute true coverage)
    supported_claims = self.repo.list_claims(
        objective_id=objective.objective_id, status=ClaimStatus.SUPPORTED
    )

    missing_fields: list[str] = []
    field_evidence_counts: dict[str, int] = {}

    for field_name in objective.required_fields:
        # Check against semantic predicate aliases
        matched_claims = self._find_claims_for_field(field_name, supported_claims)
        field_evidence_counts[field_name] = len(matched_claims)
        if len(matched_claims) == 0:
            missing_fields.append(field_name)

    total_fields = len(objective.required_fields)
    coverage = (total_fields - len(missing_fields)) / total_fields if total_fields > 0 else 1.0

    # 2. Epistemic satisfaction check (all fields present with corroborated evidence)
    if len(missing_fields) == 0 and len(supported_claims) > 0:
        return StoppingEvaluation(
            should_stop=True,
            reason="All required intelligence fields satisfied with verified claims.",
            missing_fields=[],
            coverage_score=1.0,
        )

    # 3. Budget safety boundary check
    if tasks_executed >= objective.max_tasks:
        return StoppingEvaluation(
            should_stop=True,
            reason=(
                f"Task budget reached ({tasks_executed}/{objective.max_tasks}). "
                f"Coverage: {coverage:.0%}. Missing critical fields: {missing_fields}"
            ),
            missing_fields=missing_fields,     # Accurately report missing fields!
            coverage_score=coverage,           # Accurately report true coverage!
        )

    # 4. Diminishing returns check (prevent infinite loops when info doesn't exist)
    if self._has_diminishing_returns(objective.objective_id, window=4):
        return StoppingEvaluation(
            should_stop=True,
            reason="Information saturation: last 4 tasks produced 0 new verified claims.",
            missing_fields=missing_fields,
            coverage_score=coverage,
        )

    return StoppingEvaluation(
        should_stop=False,
        reason=f"Epistemic coverage at {coverage:.0%}. Active missing fields: {missing_fields}",
        missing_fields=missing_fields,
        coverage_score=coverage,
    )
```

---

## Root Cause 6: Predicate & Schema Semantic Mismatch

### Problem Recap
- In `objective.required_fields`, the target fields are: `["manufacturer", "manufacturing_plant", "plant_head", "tech_lead", "contact_info"]`.
- The worker extraction prompt in [`prompts.py`](file:///data/shared/project/PlayGround/Argus/src/argus/worker/prompts.py#L7-L14) only standardized generic predicates: `OPERATES_FACILITY`, `LOCATED_IN`, `HAS_LEADERSHIP`, `PRODUCES_MODEL`.
- When the worker extracted a claim with predicate `HAS_LEADERSHIP` and object `"John Smith"`, the planner's evaluator checked:
  ```python
  "plant_head" in claim.predicate.lower() or "plant_head" in claim.object_value.lower()
  ```
  Neither condition was true! As a result, even if leadership was discovered, **the planner classified it as missing**.

---

### Solution 6.1: Semantic Predicate Ontology & Normalization

Define an explicit mapping table between intelligence objective fields and normalized predicates:

```python
FIELD_PREDICATE_ONTOLOGY: dict[str, list[str]] = {
    "manufacturer": [
        "IS_MANUFACTURER", "MANUFACTURES", "ACTIVE_MANUFACTURER", "OPERATES_IN_INDUSTRY"
    ],
    "manufacturing_plant": [
        "OPERATES_FACILITY", "OPERATES_PLANT", "OWNS_PLANT", "ASSEMBLY_FACILITY"
    ],
    "plant_head": [
        "HAS_PLANT_HEAD", "HAS_PLANT_MANAGER", "MANAGED_BY", "PLANT_DIRECTOR_OF",
        "SITE_LEADER_OF", "HAS_LEADERSHIP", "FACILITY_DIRECTOR"
    ],
    "tech_lead": [
        "HAS_TECH_LEAD", "HAS_CHIEF_ENGINEER", "ENGINEERING_DIRECTOR_OF",
        "TECHNICAL_LEAD_OF", "HEAD_OF_ENGINEERING", "PLANT_CHIEF_ENGINEER"
    ],
    "contact_info": [
        "HAS_CONTACT_EMAIL", "HAS_CONTACT_PHONE", "HAS_MEDIA_CONTACT",
        "HAS_PUBLIC_PHONE", "HAS_LINKEDIN_URL", "HAS_OFFICIAL_ADDRESS"
    ],
}
```

```python
def _find_claims_for_field(self, field_name: str, claims: list[Claim]) -> list[Claim]:
    """Match claims using semantic predicate ontology and keyword heuristics."""
    fn_lower = field_name.strip().lower()
    valid_predicates = set(FIELD_PREDICATE_ONTOLOGY.get(fn_lower, []))

    matched = []
    for claim in claims:
        pred_upper = claim.predicate.upper()
        # 1. Exact ontology match
        if pred_upper in valid_predicates:
            matched.append(claim)
            continue
        # 2. Substring fallback match
        if fn_lower in claim.predicate.lower() or fn_lower in claim.object_value.lower():
            matched.append(claim)
            continue
        # 3. Person entity role check
        if fn_lower in ("plant_head", "tech_lead") and "LEADERSHIP" in pred_upper:
            matched.append(claim)
    return matched
```

---

### Solution 6.2: Enhanced Worker Extraction System Prompt

Update [`WORKER_SYSTEM_PROMPT`](file:///data/shared/project/PlayGround/Argus/src/argus/worker/prompts.py) to explicitly instruct the LLM worker to isolate plant leadership and contact information:

```python
WORKER_SYSTEM_PROMPT = """You are an epistemic intelligence worker in the Argus research engine.
Your mission is to rigorously analyze web documents, assess their relevance, and extract structured entities and factual claims.

Strict Invariants:
1. Relevance Triage: Determine if this document provides substantive facts regarding the objective or task. If boilerplate/irrelevant, return is_relevant=false.
2. Grounded Claims: Every claim must be backed by a verbatim quote from the text.
3. Standardized Predicates for Industrial Intelligence:
   - For Facilities: OPERATES_FACILITY, LOCATED_IN, PRODUCES_MODEL, PLANT_CAPACITY
   - For Plant Leadership: HAS_PLANT_HEAD, HAS_PLANT_MANAGER, HAS_SITE_DIRECTOR
   - For Technical Leadership: HAS_TECH_LEAD, HAS_CHIEF_ENGINEER, HAS_ENGINEERING_LEAD
   - For Contact Details: HAS_CONTACT_EMAIL, HAS_CONTACT_PHONE, HAS_LINKEDIN_URL, HAS_FACILITY_ADDRESS
4. Entity Typing: Discovered entities MUST be categorized into:
   - company (e.g. Ford Motor Company, General Motors)
   - facility (e.g. Kentucky Truck Plant, Arlington Assembly)
   - person (e.g. Joe Hinrichs, Jane Doe)
   - contact (e.g. media@ford.com, +1-502-555-0100)
"""
```

---

## Root Cause 7: Contact Info Resolution & Verification

### Problem Recap
Corporate plant leaders frequently do not publish direct emails on open public web pages. General web crawlers either find no contact information or grab irrelevant generic customer service numbers (e.g., `1-800-FORD-USA`).

---

### Solution 7.1: Tiered Contact Resolution Engine

Argus should apply a 3-tier contact discovery heuristic:

```mermaid
flowchart TD
    Entity["Person: Plant Manager Identified"] --> Tier1{"Direct Web Search"}
    Tier1 -->|Found in Press Release / News| Verified["Verified Contact Record"]
    Tier1 -->|Not Found| Tier2{"Corporate Pattern Inference"}
    
    Tier2 --> Pattern["Company Email Pattern Detection<br/>e.g. {first}.{last}@ford.com"]
    Pattern --> MX["DNS MX Record Check"]
    MX --> Syntax["RFC 5322 Syntax Validation"]
    Syntax --> Inferred["High-Confidence Inferred Pattern"]
    
    Tier1 -->|Facility Contact| Tier3{"Official Facility Directory"}
    Tier3 --> PlantPhone["Facility Main Switchboard / Media Line"]
    PlantPhone --> Verified
```

1. **Direct Public Contact Extraction:** Search press releases and media kits for designated plant contacts.
2. **Facility Switchboard & Address Resolution:** If direct mobile/direct extension is restricted by company privacy policy, capture the **verified facility switchboard and public communications liaison**, tagged with `HAS_FACILITY_PHONE` and `HAS_MEDIA_CONTACT`.
3. **Corporate Email Pattern Inference:** Infer email addresses based on known corporate schemas (e.g., `first.last@gm.com` or `flast@ford.com`), validate against domain MX records, and record the claim with `confidence=0.85` and explicit `is_inferred=True` metadata.

---

## Complete Solution Comparison Matrix

| Layer | Original Run (Failed) | Deep Run / Proposed Solution (Fixed) | Impact on Outcome |
| :--- | :--- | :--- | :--- |
| **Search Provider** | Static mock with 6 Wikipedia URLs | Live `DuckDuckGoSearchProvider` + multi-backend cascade | Opens web access to press releases, news, and LinkedIn snippets |
| **Search Queries** | Generic keyword matching (`"ford" in q`) | Targeted search dorking (`"[Plant Name]" "plant manager"`) | Directly retrieves leadership appointments and local reporting |
| **Task Budget** | Hardcoded `max_tasks = 2` | Dynamic budget formula ($\approx 15\text{--}25$ tasks) | Allows 9 downstream leadership tasks to execute fully |
| **Crawl Breadth** | Hardcoded `max_crawl_pages_per_task = 1` | Configurable quota (3–5 pages per task) | $3\times$ to $5\times$ more intelligence documents ingested per task |
| **Source Archetypes** | Wikipedia only | 5-Tier Matrix (Press releases, SEC/OSHA, local news, trade journals) | Supplies the actual documents where leadership and contacts live |
| **Stopping Gate** | Budget check first; false `coverage=1.0` | Epistemic check first; accurate coverage & missing fields | Correctly identifies missing data and steers follow-up tasks |
| **Predicate Schema** | Generic predicates (`HAS_LEADERSHIP`) | Standardized ontology (`HAS_PLANT_HEAD`, `HAS_TECH_LEAD`) | Eliminates predicate mismatch; claims properly satisfy fields |
| **Contact Resolution** | None (expected direct emails on Wikipedia) | 3-Tier Resolution (Direct media lines, facility switchboards, email patterns) | Provides actionable contact data without violating privacy |

---

## Action Plan & Implementation Roadmap

```mermaid
gantt
    title Argus Epistemic Enhancement Roadmap
    dateFormat  YYYY-MM-DD
    section Phase 1: Engine Foundation
    Implement DuckDuckGo Live Search            :done, p1, 2026-10-04, 1d
    Configure Deep Run Script (max_tasks=15)    :done, p2, 2026-10-04, 1d
    section Phase 2: Schema & Ontology
    Update WORKER_SYSTEM_PROMPT predicates      :active, p3, 2026-10-05, 1d
    Implement FIELD_PREDICATE_ONTOLOGY in Brain :active, p4, 2026-10-05, 1d
    Fix Stopping Criteria Evaluator Bug         :active, p5, 2026-10-05, 1d
    section Phase 3: Advanced Sourcing
    Add Pre-Crawl ScoredURLRanker               :p6, 2026-10-06, 2d
    Implement Corporate Newsroom & Dorking Rules:p7, 2026-10-07, 2d
    Tiered Contact Pattern Resolver             :p8, 2026-10-08, 2d
```

### Verification & Testing
To verify the complete solution end-to-end:
1. Run `uv run python3 scripts/run_us_automotive_deep.py`
2. Inspect `data/argus_us_automotive_deep.db`:
   ```bash
   uv run python3 -c "
   import sqlite3
   db = sqlite3.connect('data/argus_us_automotive_deep.db')
   print('Entities:', db.execute('SELECT count(*) FROM entities').fetchone()[0])
   print('Claims:', db.execute('SELECT count(*) FROM claims WHERE status=\"supported\"').fetchone()[0])
   print('Leadership claims:', db.execute('SELECT count(*) FROM claims WHERE predicate LIKE \"%PLANT%\" OR predicate LIKE \"%LEAD%\"').fetchone()[0])
   "
   ```
3. Synthesize the final dossier using `uv run python3 scripts/generate_dossier_from_db.py`.
