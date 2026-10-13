# HEIMDALLR V2 — INVESTIGATION STATE SCHEMA SPECIFICATION

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "InvestigationState",
  "description": "First-class persistent, auditable investigation state for Heimdallr V2.",
  "type": "object",
  "required": [
    "investigation_id",
    "created_at",
    "updated_at",
    "objective",
    "entities",
    "relationships",
    "claims",
    "evidence",
    "questions",
    "hypotheses",
    "unresolved_questions",
    "resolved_questions",
    "contradictions",
    "temporal_states",
    "specialist_invocations",
    "active_branches",
    "completed_branches",
    "abandoned_branches",
    "research_actions",
    "observations",
    "information_gaps",
    "research_budget",
    "information_gain_history",
    "confidence_state",
    "stop_state",
    "audit_trail"
  ],
  "properties": {
    "investigation_id": {
      "type": "string",
      "description": "Unique identifier formatted as inv_[uuid12]."
    },
    "created_at": {
      "type": "string",
      "format": "date-time"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time"
    },
    "objective": {
      "type": "string",
      "description": "Natural language research objective."
    },
    "objective_contract": {
      "type": "object",
      "description": "Structured operational bounds and entity targets."
    },
    "entities": {
      "type": "object",
      "description": "Dictionary of entity name to entity profile metadata.",
      "additionalProperties": {
        "type": "object",
        "properties": {
          "name": { "type": "string" },
          "type": { "type": "string" },
          "first_seen": { "type": "string", "format": "date-time" },
          "metadata": { "type": "object" }
        },
        "required": ["name", "type", "first_seen"]
      }
    },
    "relationships": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "subject": { "type": "string" },
          "predicate": { "type": "string" },
          "object": { "type": "string" }
        },
        "required": ["subject", "predicate", "object"]
      }
    },
    "claims": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "claim_id": { "type": "string" },
          "subject": { "type": "string" },
          "predicate": { "type": "string" },
          "object": { "type": "string" },
          "status": {
            "type": "string",
            "enum": ["SUPPORTED", "INFERRED", "UNKNOWN", "NOT_FOUND", "CONTRADICTED"]
          },
          "recorded_at": { "type": "string", "format": "date-time" }
        },
        "required": ["claim_id", "subject", "predicate", "object", "status"]
      }
    },
    "evidence": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "evidence_id": { "type": "string" },
          "url": { "type": "string" },
          "title": { "type": "string" },
          "snippet": { "type": "string" },
          "source_type": { "type": "string" },
          "syndication_cluster_id": { "type": ["string", "null"] },
          "recorded_at": { "type": "string", "format": "date-time" }
        },
        "required": ["evidence_id", "url", "title", "source_type"]
      }
    },
    "questions": {
      "type": "object",
      "description": "Dictionary mapping question_id to InvestigationQuestion objects."
    },
    "hypotheses": {
      "type": "object",
      "description": "Dictionary mapping hypothesis_id to InvestigationHypothesis objects."
    },
    "unresolved_questions": {
      "type": "array",
      "items": { "type": "string" }
    },
    "resolved_questions": {
      "type": "array",
      "items": { "type": "string" }
    },
    "contradictions": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "contradiction_id": { "type": "string" },
          "claim_a": { "type": "object" },
          "claim_b": { "type": "object" },
          "status": { "type": "string", "enum": ["UNRESOLVED", "RESOLVED"] }
        },
        "required": ["contradiction_id", "claim_a", "claim_b", "status"]
      }
    },
    "temporal_states": {
      "type": "array",
      "items": { "type": "object" }
    },
    "specialist_invocations": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "specialist": { "type": "string", "enum": ["corporate", "infrastructure", "identity"] },
          "query": { "type": "string" },
          "timestamp": { "type": "string", "format": "date-time" }
        },
        "required": ["specialist", "query", "timestamp"]
      }
    },
    "active_branches": {
      "type": "array",
      "items": { "type": "string" }
    },
    "completed_branches": {
      "type": "array",
      "items": { "type": "string" }
    },
    "abandoned_branches": {
      "type": "array",
      "items": { "type": "string" }
    },
    "research_actions": {
      "type": "array",
      "items": { "type": "object" }
    },
    "observations": {
      "type": "array",
      "items": { "type": "object" }
    },
    "information_gaps": {
      "type": "array",
      "items": { "type": "object" }
    },
    "research_budget": {
      "type": "object",
      "properties": {
        "max_steps": { "type": "integer" },
        "steps_taken": { "type": "integer" },
        "max_searches": { "type": "integer" },
        "searches_count": { "type": "integer" },
        "max_tokens": { "type": "integer" },
        "tokens_consumed": { "type": "integer" },
        "cost_usd": { "type": "number" },
        "consecutive_zero_gains": { "type": "integer" }
      },
      "required": ["max_steps", "steps_taken", "cost_usd"]
    },
    "information_gain_history": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "step": { "type": "integer" },
          "action_id": { "type": "string" },
          "information_gain": { "type": "number" }
        },
        "required": ["step", "action_id", "information_gain"]
      }
    },
    "confidence_state": {
      "type": "object",
      "properties": {
        "overall_confidence": { "type": "number" },
        "confirmed_claims_count": { "type": "integer" },
        "tentative_claims_count": { "type": "integer" },
        "contradicted_claims_count": { "type": "integer" },
        "unresolved_critical_gaps": { "type": "integer" },
        "epistemic_calibration_score": { "type": "number" }
      },
      "required": ["overall_confidence", "confirmed_claims_count"]
    },
    "stop_state": {
      "type": "object",
      "properties": {
        "is_stopped": { "type": "boolean" },
        "stop_reason": {
          "type": "string",
          "enum": [
            "IN_PROGRESS",
            "OBJECTIVE_SATISFIED",
            "SUFFICIENT_EVIDENCE",
            "NO_INFORMATION_GAIN",
            "BUDGET_EXHAUSTED_WITH_ACCEPTABLE_COVERAGE",
            "BUDGET_EXHAUSTED_WITH_CRITICAL_MISSING_FIELDS",
            "UNRESOLVABLE_CONTRADICTION",
            "INFRASTRUCTURE_FAILURE",
            "SAFETY_STOP"
          ]
        },
        "stopped_at": { "type": ["string", "null"] },
        "stopping_rationale": { "type": "string" },
        "satisfaction_ratio": { "type": "number" },
        "budget_exhausted": { "type": "boolean" },
        "unresolvable_contradiction_detected": { "type": "boolean" }
      },
      "required": ["is_stopped", "stop_reason"]
    },
    "audit_trail": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "entry_id": { "type": "string" },
          "timestamp": { "type": "string", "format": "date-time" },
          "action_type": { "type": "string" },
          "actor": { "type": "string" },
          "details": { "type": "object" },
          "rationale": { "type": "string" }
        },
        "required": ["entry_id", "timestamp", "action_type", "actor"]
      }
    }
  }
}
```
