# Research Objective & Execution Architecture

## 1. Research Query Example

> [!NOTE]
> **Sample User Prompt:**  
> *"Research the US-origin automotive/automobile manufacturing industry. Identify relevant manufacturers and their US manufacturing plants. For each plant, find their head, tech lead, and their contact information."*

---

## 2. Objective Hierarchy & Task Decomposition

The high-level research objective is recursively decomposed into targeted, executable research tasks.

### Visual Hierarchy

```mermaid
graph TD
    classDef objective fill:#1e40af,stroke:#1d4ed8,color:#ffffff,font-weight:bold,rx:6px,ry:6px;
    classDef task fill:#f8fafc,stroke:#94a3b8,color:#0f172a,stroke-width:1.5px,rx:6px,ry:6px;

    ROOT["🎯 <b>OBJECTIVE</b><br/>Find US automobile manufacturers and their plants"]:::objective

    T1["📋 <b>TASK</b><br/>Find US-origin automobile manufacturers"]:::task
    T2["📋 <b>TASK</b><br/>Find Ford manufacturing plants"]:::task
    T3["📋 <b>TASK</b><br/>Find Kentucky Truck Plant address"]:::task
    T4["📋 <b>TASK</b><br/>Find current IT leader at Plant X"]:::task

    ROOT --> T1
    ROOT --> T2
    ROOT --> T3
    ROOT --> T4
```

### Tree View

```text
OBJECTIVE
Find US automobile manufacturers and their plants
 │
 ├── TASK
 │   Find US-origin automobile manufacturers
 │
 ├── TASK
 │   Find Ford manufacturing plants
 │
 ├── TASK
 │   Find Kentucky Truck Plant address
 │
 └── TASK
     Find current IT leader at Plant X
```

---

## 3. Core Research Dimensions

Every research objective is scoped and evaluated across six fundamental dimensions:

| Dimension | Core Question | Description & Focus |
| :--- | :--- | :--- |
| **Target** | *What is being searched?* | The specific entities, industry sectors, or information targets. |
| **Rationale** | *Why is it being searched?* | The intent, motivation, and underlying goal of the query. |
| **Decomposition** | *How will it be broken down?* | The strategy for partitioning the objective into atomic, executable tasks. |
| **Deliverables** | *What are the expected answers/results?* | The required schema, entity attributes, and output structure. |
| **Validation** | *How will results be verified?* | Provenance tracking, source corroboration, and accuracy checks. |
| **Boundaries** | *What constraints and rules exist?* | Budget limits, source policies, security rules, and exploration caps. |

---

## 4. Research Run Lifecycle & Architecture

The execution architecture coordinates the research run from objective intake and policy enforcement through tool orchestration, evidence collection, verification, and final output generation.

### Architecture Flowchart

```mermaid
flowchart TD
    classDef runNode fill:#2563eb,stroke:#1d4ed8,stroke-width:2px,color:#ffffff,font-weight:bold,rx:6px,ry:6px;
    classDef mainNode fill:#0284c7,stroke:#0369a1,stroke-width:2px,color:#ffffff,font-weight:bold,rx:6px,ry:6px;
    classDef policyNode fill:#7c3aed,stroke:#6d28d9,stroke-width:2px,color:#ffffff,font-weight:bold,rx:6px,ry:6px;
    classDef itemNode fill:#f8fafc,stroke:#cbd5e1,stroke-width:1px,color:#1e293b,rx:4px,ry:4px;
    classDef processNode fill:#f0fdf4,stroke:#22c55e,stroke-width:1.5px,color:#15803d,font-weight:600,rx:6px,ry:6px;
    classDef terminalNode fill:#059669,stroke:#047857,stroke-width:2px,color:#ffffff,font-weight:bold,rx:6px,ry:6px;

    RUN["🚀 RESEARCH RUN"]:::runNode

    subgraph SubObjective ["🎯 Research Scoping"]
        OBJ["RESEARCH OBJECTIVE"]:::mainNode
        OBJ_ITEMS["• Intent<br/>• Purpose<br/>• Expected Output<br/>• Scope<br/>• Constraints"]:::itemNode
        OBJ --- OBJ_ITEMS
    end

    subgraph SubPolicies ["🛡️ Governance & Rules"]
        POL["RESEARCH POLICIES"]:::policyNode
        BGT["💰 Budget"]:::itemNode
        VRF["🔍 Verify"]:::itemNode
        SEC["🔒 Security"]:::itemNode
        POL --> BGT
        POL --> VRF
        POL --> SEC
    end

    RUN --> OBJ
    RUN --> POL

    OBJ_ITEMS --> CTRL["⚙️ RESEARCH CONTROLLER"]:::processNode
    BGT & VRF & SEC --> CTRL

    CTRL --> TASKS["📋 RESEARCH TASKS"]:::processNode
    TASKS --> TOOLS["🛠️ TOOLS"]:::processNode
    TOOLS --> EVIDENCE["🔎 EVIDENCE"]:::processNode
    EVIDENCE --> VERIFICATION["✅ VERIFICATION"]:::processNode
    VERIFICATION --> STOPPING["🛑 STOPPING"]:::processNode
    STOPPING --> FINAL["📦 FINAL OUTPUT"]:::terminalNode
```

### Architecture Diagram (ASCII)

```text
                    RESEARCH RUN
                         │
        ┌────────────────┴────────────────┐
        │                                 │
        ▼                                 ▼
RESEARCH OBJECTIVE                RESEARCH POLICIES
        │                                 │
        │                         ┌───────┼────────┐
        │                         ↓       ↓        ↓
        │                      Budget  Verify   Security
        │
        ├── Intent
        ├── Purpose
        ├── Expected Output
        ├── Scope
        └── Constraints
                         │
                         ▼
                 RESEARCH CONTROLLER
                         │
                         ▼
                  RESEARCH TASKS
                         │
                         ▼
                      TOOLS
                         │
                         ▼
                    EVIDENCE
                         │
                         ▼
                   VERIFICATION
                         │
                         ▼
                     STOPPING
                         │
                         ▼
                    FINAL OUTPUT
```

---

## 5. Pipeline Component Reference

- **Research Run:** The top-level orchestration lifecycle managing the entire investigation.
- **Research Objective:** Formalizes the prompt into structured intent, purpose, expected schema, scope, and constraints.
- **Research Policies:** Enforces operational guardrails across resource budget (tokens/time/requests), verification thresholds, and security/safety limits.
- **Research Controller:** The central engine that coordinates task creation, dispatch, and state tracking.
- **Research Tasks:** Individual atomic actions generated dynamically to address knowledge gaps.
- **Tools:** Search engines, web fetchers, document parsers, and scrapers used to gather raw context.
- **Evidence:** Extracted claims, entities, relationships, and source citations.
- **Verification:** Corroboration engine checking evidence consistency, source credibility, and conflict detection.
- **Stopping Condition:** Criteria evaluation to determine if research goals are satisfied or limits are reached.
- **Final Output:** Structured, verified knowledge dataset (JSON, SQLite, reports) with full provenance.