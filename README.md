# HEIMDALLR V4

> **Sovereign Intelligence Platform & Autonomous Multi-Specialist OSINT Engine**

[![Python Version](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![Package Manager](https://img.shields.io/badge/manager-uv-purple.svg)](https://github.com/astral-sh/uv)
[![Test Suite](https://img.shields.io/badge/tests-180%2B%20passing-brightgreen.svg)]()
[![Security](https://img.shields.io/badge/security-SSRF%20Hardened-orange.svg)]()

**Heimdallr** (`argus`) is an autonomous, evidence-backed open-source intelligence (OSINT) and investigation platform designed for deep, auditable inquiry across corporate, infrastructure, developer identity, regulatory, and public web domains.

Unlike naive scrapers or prompt-only LLM wrappers, Heimdallr executes an autonomous investigation loop: it decomposes complex intelligence objectives into testable hypotheses, discovers and retrieves authoritative sources across specialized domains, verifies empirical claims against full-document evidence, and exports cryptographic-grade audit dossiers in multi-tab Excel workbooks.

---

## Architectural Pillars

1. **Evidence-Backed Epistemic Rigor**  
   Strict architectural separation between discovered candidate URLs, fully retrieved documents, candidate claims, and verified findings. Search snippets are never conflated with complete evidence, and missing sources never count as disproof.

2. **Autonomous Multi-Specialist Collaboration**  
   Cross-domain inquiry coordinated by dynamic capability routing. Domain specialists (Corporate Filings, DNS & CT Logs, Developer Personas, Sanctions & Offshore Disclosures, Darknet Services) collaborate over a shared knowledge topology.

3. **General-Purpose Investigation Execution**  
   Every query—whether corporate reconnaissance, literature research, or technical protocol inquiry—is dynamically planned and executed through the core `InvestigationEngine` without hardcoded synthetic interceptors or canned benchmarks.

4. **Persistent Intelligence Architecture**  
   Deterministic audit logging, structured claim-evidence provenance graphs, and automated multi-tab Excel (`.xlsx`) dossier generation for verifiable investigation trails.

---

## System Architecture

```
                                  Target Request / Objective
                                               │
                                               ▼
                                ┌──────────────────────────────┐
                                │    OSINT Terminal / CLI      │
                                │   (Interactive or Batch)     │
                                └──────────────┬───────────────┘
                                               │
                                               ▼
                                ┌──────────────────────────────┐
                                │     InvestigationEngine      │
                                │   (State & Lifecycle Loop)   │
                                └──────────────┬───────────────┘
                                               │
                        ┌──────────────────────┴──────────────────────┐
                        ▼                                             ▼
         ┌─────────────────────────────┐               ┌─────────────────────────────┐
         │    InvestigationPlanner     │               │     CapabilityRegistry      │
         │  (Question Decomposition &  │               │   (Specialist Matching &    │
         │     Dynamic Action Plan)    │               │    Implementation Select)   │
         └──────────────┬──────────────┘               └──────────────┬──────────────┘
                        │                                             │
                        └──────────────────────┬──────────────────────┘
                                               │
                                               ▼
                                ┌──────────────────────────────┐
                                │    Specialist Dispatches     │
                                │  Corporate | Infra | Identity│
                                │  Sanctions | General Web     │
                                └──────────────┬───────────────┘
                                               │
                                               ▼
                                ┌──────────────────────────────┐
                                │   Two-Tier Fetcher & SSRF    │
                                │  (HTTPX + Playwright Guard)  │
                                └──────────────┬───────────────┘
                                               │
                                               ▼
                                ┌──────────────────────────────┐
                                │    Evidence & Claim Audit    │
                                │  (Semantic Auditor & State)  │
                                └──────────────┬───────────────┘
                                               │
                                               ▼
                                ┌──────────────────────────────┐
                                │    Dossier Export (.xlsx)    │
                                │   Entities | Claims | Trace  │
                                └──────────────────────────────┘
```

---

## Core Specialists & Capabilities

Heimdallr routes tasks dynamically to targeted specialists based on query semantics:

* **Corporate Registry & Filings Specialist**:
  * SEC EDGAR parsing (Form 10-K, 10-Q, 8-K).
  * Exhibit 21 subsidiary mapping and parent-subsidiary hierarchy resolution.
  * Executive officer roster extraction, board tenure tracking, and UK Companies House integration.
* **Infrastructure & Perimeter Reconnaissance Specialist**:
  * Passive DNS enumeration and IP/ASN mapping.
  * Certificate Transparency (CT) log analysis (`crt.sh`) and Subject Alternative Name (SAN) inspection.
  * Subdomain discovery and mail exchange (MX) topology extraction.
* **Developer Identity & Attribution Specialist**:
  * Multi-platform handle correlation and alias resolution (Blackbird OSINT engine).
  * GitHub commit histories, public key fingerprints (SSH/GPG), and author email extraction.
  * Prevention of false conflations through strict corroboration thresholds.
* **Sanctions, AML & Beneficial Ownership Specialist**:
  * Automated screening against international sanctions databases (OFAC SDN, UK OFSI, OpenSanctions).
  * Politically Exposed Persons (PEP) correlation and offshore ownership cross-referencing.
* **Two-Tier Web Fetcher & SSRF-Safe Network Layer**:
  * Tier 1: High-throughput asynchronous HTTPX fetcher.
  * Tier 2: Headless Chromium (Playwright) dynamic renderer for JavaScript-heavy targets.
  * Network boundary defense: Proactively blocks RFC 1918 private subnets, loopback addresses (`127.0.0.0/8`, `::1`), cloud metadata endpoints (`169.254.169.254`, `168.63.129.16`), and DNS rebinding attacks at both socket and browser route levels.

---

## Epistemic Claim Statuses

Claims extracted during an investigation are scored and assigned strict epistemic statuses:

| Epistemic Status | Description |
| :--- | :--- |
| **`SUPPORTED`** | Empirically verified by primary or authoritative source evidence with verbatim passage grounding. |
| **`CORROBORATED`** | Cross-verified across multiple independent sources. |
| **`REFUTED`** | Contradicted by authoritative source evidence; contra-hypotheses accepted. |
| **`INCONCLUSIVE`** | Conflicting evidence or insufficient depth to determine objective truth. |
| **`NOT_FOUND`** | Target entity or specific attribute not found after exhaustive domain search. |
| **`UNVERIFIED`** | Discovered candidate claim awaiting full document retrieval and semantic audit. |

---

## Autonomous Deep Research by Default

Heimdallr performs **autonomous deep research by default**. Operators do not need to manually select investigation profiles or scan depths:
- **Autonomous Specialist Coordination**: The engine dynamically routes across domain specialists (Corporate, Infrastructure, Developer Identity, Sanctions) and live web retrieval based on the objective and emerging evidence.
- **Adaptive Investigation Depth**: Research pursues leads until the objective is satisfied, sufficient evidence is gathered, or an internal safety safeguard limit (15 steps) is reached.
- **Truthful Epistemic Disclosures**: Scan summaries disclose the exact termination reason, counts of unresolved questions, and documented limitations.

---

## Project Layout

```
Argus/
├── pyproject.toml              # Project dependencies and CLI entrypoints
├── src/
│   └── argus/
│       ├── terminal.py         # Heimdallr V4 OSINT Terminal & CLI interface
│       ├── investigation/      # Core investigation engine, planner & state
│       │   ├── orchestrator.py # InvestigationEngine and action execution loop
│       │   ├── planner.py      # InvestigationPlanner & question decomposition
│       │   ├── stopping.py     # Truthful stopping criteria evaluators
│       │   └── state.py        # InvestigationState, Claims, and Evidence
│       ├── specialists/        # Domain-specific intelligence specialists
│       │   ├── corporate/      # SEC EDGAR, Companies House, executive profiles
│       │   ├── infrastructure/ # Passive DNS, crt.sh, ASN, SANs
│       │   ├── identity/       # GitHub, key correlation, Blackbird integration
│       │   └── sanctions/      # OFAC SDN, UK OFSI screening
│       ├── capability_registry/# Dynamic capability routing & adapter matching
│       ├── crawler/            # Two-tier HTTPX/Playwright fetcher with SSRF guards
│       ├── search/             # Search engines (DuckDuckGo, SearXNG, Google News)
│       ├── verifier/           # Epistemic claim verifier & semantic auditor
│       └── export/             # Multi-tab Excel (.xlsx) dossier generator
├── tests/                      # Full test and validation suite (180+ tests)
└── exports/                    # Default destination for generated intelligence dossiers
```

---

## Installation & Setup

Heimdallr is built for **Python >= 3.12** using [`uv`](https://github.com/astral-sh/uv) for fast, deterministic dependency management.

```bash
# 1. Clone repository
git clone https://github.com/Mihirmaru22/Heimdallr.git
cd Heimdallr

# 2. Sync virtual environment and dependencies
uv sync

# 3. (Optional) Install Playwright browser dependencies for Tier-2 dynamic rendering
uv run playwright install --with-deps chromium
```

---

## Quick Start & CLI Usage

### 1. Interactive Terminal Session

Launch the interactive terminal session with live progress tracking, rich status dashboards, and autonomous deep research:

```bash
uv run osint-terminal
```

### 2. Direct CLI Non-Interactive Execution

Run investigations headlessly for CI pipelines, automated recon jobs, or scripted investigations:

```bash
# Corporate / Executive Investigation
uv run osint-terminal \
  --target "Research Apex Technologies Group leadership roster and corporate structure" \
  --output exports/apex_dossier.xlsx \
  --no-interactive

# Technical Protocol / Literature Investigation
uv run osint-terminal \
  --target "Raft consensus protocol Stanford Diego Ongaro" \
  --no-interactive

# Live Web Intelligence Probe
uv run osint-terminal \
  --target "List out companies in Gujarat using SAP ERP" \
  --no-interactive
```

### 3. CLI Options Reference

| Flag | Short | Default | Description |
| :--- | :---: | :---: | :--- |
| `--target` | `-t` | Prompted | Target entity, organization, person, or research question |
| `--output` | `-o` | Auto-generated | Destination path for the generated Excel intelligence report (`.xlsx`) |
| `--no-interactive` | — | `False` | Run headlessly without user prompts |
| `--version` | `-v` | — | Display platform generation and package version |

---

## Programmatic API Usage

Heimdallr can be integrated directly into Python intelligence pipelines:

```python
from argus.investigation.orchestrator import InvestigationEngine
from argus.export.excel_exporter import OSINTExcelExporter

# Initialize sovereign investigation engine
engine = InvestigationEngine()

# Start an investigation with a defined action budget
state = engine.start_investigation(
    objective="Research Apex Technologies Group executive officers and subsidiaries",
    contract={"max_steps": 10},
)

# Execute the autonomous investigation loop
while not state.stop_state.is_stopped:
    state, finished = engine.execute_step(state)
    if finished:
        break

# Inspect verified epistemic findings
print(f"Investigation Stop Reason: {state.stop_state.stop_reason}")
print(f"Total Discovered Entities: {len(state.entities)}")
print(f"Total Verified Claims:     {len(state.claims)}")
print(f"Authoritative Sources:     {len(state.evidence)}")

for claim in state.claims.values():
    if claim.epistemic_status == "SUPPORTED":
        print(f"[SUPPORTED] {claim.subject} -> {claim.predicate} -> {claim.object}")
        print(f"            Citation: {claim.primary_source_url}")

# Export multi-tab Excel dossier
exporter = OSINTExcelExporter()
export_path = exporter.export_investigation(
    results_data={
        "target": state.objective,
        "mode": "chain",
        "state": state,
        "claims": list(state.claims.values()),
        "entities": state.entities,
        "evidence": list(state.evidence.values()),
        "actions": state.history,
    },
    output_filepath="exports/investigation_dossier.xlsx",
)
print(f"Dossier exported to: {export_path}")
```

---

## Intelligence Dossier Structure

Every completed investigation compiles a comprehensive, multi-tab Excel intelligence dossier (`.xlsx`):

1. **Executive Dossier**: High-level intelligence brief, target definition, objective status, confidence scores, and entity count breakdown.
2. **Verified Intelligence**: Structured claim triples (`Subject`, `Predicate`, `Object`), confidence scores, epistemic status badges (`SUPPORTED`, `REFUTED`, `NOT_FOUND`), and primary citation URLs.
3. **Entity Dossier**: Catalog of all discovered organizations, personnel, infrastructure assets, and technical entities with relationship links.
4. **Evidence & Citations**: Complete register of retrieved documents, source types, HTTP response metadata, and verbatim source passages.
5. **Audit & Action Trail**: Chronological, immutable record of every planned action, specialist dispatch, execution duration, and stopping rationale.

---

## Verification & Testing

Heimdallr is verified by an extensive regression suite covering investigation orchestration, specialist contracts, network safety, and terminal interfaces:

```bash
# Run full investigation orchestration suite (180 tests)
uv run pytest tests/investigation/

# Run terminal interface & CLI regression suite (23 tests)
uv run pytest tests/test_terminal_interface.py

# Run network security, SSRF boundaries & AST sandbox tests
uv run pytest tests/test_security_hardening.py tests/test_browser_ssrf_boundary.py

# Run complete test suite across all subsystems
uv run pytest
```

---

## License

This project is licensed under the terms defined in the repository's license configuration.
