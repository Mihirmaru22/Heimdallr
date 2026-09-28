                         ┌─────────────────────--─┐
                         │   RESEARCH OBJECTIVE   │
                         │                        │ 
                         │ "Find US-origin auto   │
                         │ manufacturers + plants"│
                         └──────────┬────────────-┘
                                    │
                                    ▼
                    ┌───────────────────────────┐
                    │      RESEARCH BRAIN       │
                    │                           │
                    │ What do I know?           │
                    │ What don't I know?        │
                    │ What should I investigate │
                    │ next?                     │
                    └─────────────┬─────────────┘
                                  │
                       creates research tasks
                                  │
             ┌────────────────────┼────────────────────┐
             ▼                    ▼                    ▼
      ┌─────────────┐      ┌─────────────┐      ┌─────────────-┐
      │ Find Plants │      │ Find Leader │      │ Find Products│
      └──────┬──────┘      └──────┬──────┘      └──────┬─────-─┘
             │                    │                    │
             └────────────────────┼────────────────────┘
                                  ▼
                     ┌────────────────────────┐
                     │       WEB WORLD        │
                     │                        │
                     │ Search → Pages → Links │
                     │        → Documents     │
                     └───────────┬────────────┘
                                 │
                                 ▼
                     ┌────────────────────────┐
                     │    EXTRACT KNOWLEDGE   │
                     │                        │
                     │ Entities               │
                     │ Claims                 │
                     │ Relationships          │
                     └───────────┬────────────┘
                                 │
                                 ▼
              ┌────────────────────────────────────────┐
              │            EVIDENCE GRAPH              │
              │                                        │
              │  Plant ──HAS_MANAGER──> Person         │
              │    │                     │             │
              │    └──LOCATED_AT──> Address            │
              │                          │             │
              │       every claim ─────-─┘             │
              │          has evidence                  │
              └──────────────────┬─────────────────────┘
                                 │
                                 ▼
                     ┌────────────────────────┐
                     │       VERIFY           │
                     │                        │
                     │ ✓ Supported            │
                     │ ✓ Corroborated         │
                     │ ⚠ Conflicting          │
                     │ ? Unknown              │
                     │ ⏳ Stale               │
                     └───────────┬────────────┘
                                 │
                       ┌─────────┴─────────┐
                       │                   │
                 More needed?          Sufficient?
                       │                   │
                       ▼                   ▼
               ┌──────────────┐    ┌──────────────┐
               │ NEW RESEARCH │    │     STOP     │
               │    TASKS     │    │              │
               └──────┬───────┘    └──────┬───────┘
                      │                    │
                      └───────↩────────────┘
                                           │
                                           ▼
                              ┌──────────────────────┐
                              │   VERIFIED DATASET   │
                              │                      │
                              │ JSON / SQLite        │
                              │ + provenance         │
                              │ + evidence           │
                              └──────────────────────┘