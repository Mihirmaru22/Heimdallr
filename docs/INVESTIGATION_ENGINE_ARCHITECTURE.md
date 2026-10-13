# HEIMDALLR V2 — INVESTIGATION ENGINE ARCHITECTURE

```
                                      +------------------------------------+
                                      |        INVESTIGATION OBJECTIVE      |
                                      +------------------------------------+
                                                         |
                                                         v
                                      +------------------------------------+
                                      |       InvestigationPlanner         |
                                      |   - Decompose into Questions       |
                                      |   - Formulate Hypotheses           |
                                      |   - Define Evidence Requirements   |
                                      +------------------------------------+
                                                         |
                                                         v
+------------------------+            +------------------------------------+
|  InvestigationStore    |<---------->|        InvestigationState          |
|  - JSON State Snapshot |            |   - Entities, Claims, Evidence     |
|  - JSONL Audit Stream  |            |   - Question / Hypothesis Graphs   |
|  - Crash Recovery      |            |   - Active & Completed Branches    |
+------------------------+            +------------------------------------+
                                                         |
                                                         v
                                      +------------------------------------+
                                      |     InformationGainEstimator       |
                                      |   - Score Candidate Actions        |
                                      |   - Prioritize by Expected Value   |
                                      +------------------------------------+
                                                         |
                                                         v
                                      +------------------------------------+
                                      |        InvestigationEngine         |
                                      |   - Action Dispatch & Orchestration|
                                      +------------------------------------+
                                        /                |               \
                                       /                 |                \
                                      v                  v                 v
                       +-------------------+   +-------------------+   +-------------------+
                       | CorporateProbe    |   | InfrastructureProbe|  | IdentityProbe     |
                       | Specialist        |   | Specialist        |   | Specialist        |
                       | - SEC EDGAR / UK  |   | - CT Logs / SANs  |   | - Bio / Profiles  |
                       +-------------------+   +-------------------+   +-------------------+
                                       \                 |                /
                                        \                |               /
                                         v               v              v
                                      +------------------------------------+
                                      |       Observation Processing       |
                                      |   - Evidence Ingestion             |
                                      |   - Entity Grounding               |
                                      |   - Relational Extraction          |
                                      |   - Epistemic Belief Update        |
                                      +------------------------------------+
                                                         |
                                                         v
                                      +------------------------------------+
                                      |    Multi-Specialist Chaining       |
                                      |   Corporate -> Infra -> Identity   |
                                      +------------------------------------+
                                                         |
                                                         v
                                      +------------------------------------+
                                      |    InvestigationStoppingPolicy     |
                                      |   - OBJECTIVE_SATISFIED?           |
                                      |   - SUFFICIENT_EVIDENCE?           |
                                      |   - NO_INFORMATION_GAIN?           |
                                      |   - BUDGET_EXHAUSTED?              |
                                      +------------------------------------+
                                                         |
                                       +-----------------+-----------------+
                                       |                                   |
                                  [Continue]                            [Stop]
                                       |                                   |
                                       v                                   v
                             (Next Research Cycle)                 (Final Dossier)
```

---

### Component Specifications

#### 1. InvestigationState ([state.py](file:///data/shared/project/PlayGround/Argus/src/argus/investigation/state.py))
- **`investigation_id`**: Globally unique UUID tracking session lifecycle.
- **`entities`**: Normalized map of discovered entities with typology, first-seen timestamps, and attribute metadata.
- **`relationships`**: Triple store `(subject, predicate, object)` encoding corporate hierarchies, infrastructure ties, and employment history.
- **`claims`**: Grounded statements bound to epistemic confidence statuses.
- **`evidence`**: Immutable provenance store tracking document URLs, titles, snippets, source types, and syndication cluster IDs.
- **`questions` / `hypotheses`**: Directed topological graph of unresolved and resolved queries.
- **`contradictions`**: Conflict ledger recording competing claims across sources.
- **`temporal_states`**: Historical tenure and restatement assertions bound to explicit date intervals.
- **`research_budget`**: Step counter, token consumption, marginal cost telemetry, and plateau tracking.
- **`audit_trail`**: Immutable append-only log recording every decision and state transition.

#### 2. InvestigationQuestion & Dependencies ([question.py](file:///data/shared/project/PlayGround/Argus/src/argus/investigation/question.py))
- Questions maintain explicit prerequisites (`dependencies: list[str]`).
- A question cannot be selected for execution while `is_blocked(resolved_question_ids)` returns `True`.
- Questions spawn child questions dynamically upon observation (e.g. general executive roster question spawns 20 individual executive verification questions).

#### 3. InvestigationHypothesis & Symmetrical Scrutiny ([hypothesis.py](file:///data/shared/project/PlayGround/Argus/src/argus/investigation/hypothesis.py))
- Hypotheses specify both `supporting_evidence_requirements` and `refuting_evidence_requirements`.
- Status transitions: `UNTESTED` → `SUPPORTED`, `WEAKLY_SUPPORTED`, `CONTRADICTED`, `INCONCLUSIVE`, `SUPERSEDED`.
- Conflicting evidence triggers recalculation rather than confirmation bias.

#### 4. InformationGainEstimator ([information_gain.py](file:///data/shared/project/PlayGround/Argus/src/argus/investigation/information_gain.py))
Heuristic scoring function:
$$\text{Expected Value} = \frac{\text{Relevance} \times \text{Unresolved Need} \times \text{Evidence Value} \times \text{Discovery Probability} \times \text{Contradiction Resolution Value}}{\text{Cost}}$$
Actions yielding low expected gain are filtered or deferred in favor of high-yield investigative steps.

#### 5. Multi-Specialist Chaining Pipeline ([orchestrator.py](file:///data/shared/project/PlayGround/Argus/src/argus/investigation/orchestrator.py))
Demonstrated end-to-end chain:
1. **Corporate Specialist** retrieves SEC Exhibit 21 subsidiary schedule: discovers `Apex Technologies Europe Ltd` (UK).
2. **Corporate Discovery** triggers next-hop **Infrastructure Question**: queries DNS/CT log for `apex-telemetry.co.uk`.
3. **Infrastructure Specialist** retrieves CT log: discovers SAN hostname `telemetry-cluster-01.apex-telemetry.co.uk` and administrator contact `Rachel Thorne` (`rthorne-sec@apex-tech.com`).
4. **Infrastructure Discovery** triggers next-hop **Identity Question**: probes Rachel Thorne's professional background.
5. **Identity Specialist** retrieves executive profile: verifies former employer `Cyberspace Defense Corp` and role as CISO.
6. **Corporate Specialist** cross-verifies executive appointment at parent company `Apex Technologies Group Inc`.

#### 6. Persistence & Crash Resumption ([store.py](file:///data/shared/project/PlayGround/Argus/src/argus/investigation/store.py))
- Atomic JSON disk persistence under `storage/investigations/{investigation_id}.json`.
- Concurrent append-only JSONL streaming under `storage/investigations/{investigation_id}_audit.jsonl`.
- Long-running investigations survive process SIGTERM or crashes; calling `resume_investigation(investigation_id)` deterministically restores the exact knowledge graph, budget counters, and active branches.
