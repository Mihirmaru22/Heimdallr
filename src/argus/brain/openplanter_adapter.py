"""OpenPlanter Adapter for Argus Research Brain.

Challenges Argus Research Brain by providing recursive sub-agent delegation,
acceptance-criteria-driven subtask execution, and prompt-guided entity resolution
based on the OpenPlanter investigation engine (ShinMegamiBoson/OpenPlanter).
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from argus.brain.base import BaseResearchBrain
from argus.brain.models import (
    DossierEntitySummary,
    ResearchDossier,
    StoppingEvaluation,
)
from argus.domain.claim import Claim, ClaimStatus
from argus.domain.event import EventType, ResearchEvent
from argus.domain.objective import ResearchObjective
from argus.domain.task import ResearchTask, TaskStatus
from argus.llm.provider import LLMProvider
from argus.storage.repository import ArgusRepository

logger = logging.getLogger(__name__)


class OpenPlanterSubtask(BaseModel):
    """OpenPlanter recursive subtask model with explicit acceptance criteria."""

    title: str = Field(..., description="Investigation subtask title")
    description: str = Field(..., description="Actionable scope and questions")
    search_queries: list[str] = Field(default_factory=list, description="Targeted OSINT queries")
    acceptance_criteria: str = Field(..., description="Verification condition to judge success")
    priority: int = Field(default=5, ge=1, le=10)


class OpenPlanterDecompositionPayload(BaseModel):
    """Structured response from OpenPlanter recursive planner."""

    subtasks: list[OpenPlanterSubtask] = Field(..., description="Recursive investigative subtasks")
    investigation_hypothesis: str = Field(..., description="High-level working hypothesis")


OPENPLANTER_SYSTEM_PROMPT = """You are OpenPlanter, an open-source recursive AI investigation agent.
Your objective is to conduct thorough OSINT and forensic entity intelligence.
Decompose complex objectives into atomic subtasks, each equipped with explicit acceptance criteria
and search queries. Focus on identifying corporate relationships, facilities, executive roles, and operational details."""


class OpenPlanterAdapter(BaseResearchBrain):
    """Adapts OpenPlanter recursive investigation engine to the Argus ResearchBrain contract."""

    def __init__(
        self,
        repo: ArgusRepository,
        llm: LLMProvider,
        system1: Any = None,  # OpenPlanter does not use Argus System 1, retained for signature compatibility
        max_depth: int = 4,
    ) -> None:
        self.repo = repo
        self.llm = llm
        self.system1 = None  # OpenPlanter operates purely through LLM planning and recursion
        self.max_depth = max_depth

    async def plan_initial_tasks(
        self, objective: ResearchObjective
    ) -> list[ResearchTask]:
        """Decompose objective into OpenPlanter recursive subtasks."""
        prompt = (
            f"TARGET: {objective.target} ({objective.target_type})\n"
            f"GOAL: {objective.intelligence_goal}\n"
            f"REQUIRED FIELDS: {', '.join(objective.required_fields) if objective.required_fields else 'general'}\n\n"
            f"Decompose this investigation into recursive subtasks with clear acceptance criteria."
        )

        try:
            payload: OpenPlanterDecompositionPayload = await self.llm.generate_structured(
                prompt=prompt,
                response_model=OpenPlanterDecompositionPayload,
                system_prompt=OPENPLANTER_SYSTEM_PROMPT,
            )
            subtasks = payload.subtasks
        except Exception:
            # Fallback to standard deterministic planning if LLM provider has restricted schema support
            subtasks = [
                OpenPlanterSubtask(
                    title=f"Investigate operations and facilities for {objective.target}",
                    description=f"Map primary operations and facilities for {objective.target}.",
                    search_queries=[
                        f"{objective.target} operations facilities",
                        f"{objective.target} corporate headquarters",
                    ],
                    acceptance_criteria=f"Identified core facilities and headquarters for {objective.target}",
                    priority=8,
                )
            ]

        created_tasks: list[ResearchTask] = []
        for sub in subtasks:
            desc = (
                f"{sub.description}\n\n"
                f"Acceptance Criteria: {sub.acceptance_criteria}\n\n"
                f"Search Queries:\n" + "\n".join(f"- {q}" for q in sub.search_queries)
            )

            task = ResearchTask(
                objective_id=objective.objective_id,
                title=sub.title,
                description=desc,
                status=TaskStatus.READY,
                priority=sub.priority,
                depth=1,
            )
            self.repo.save_task(task)
            self.repo.record_event(
                ResearchEvent(
                    objective_id=objective.objective_id,
                    task_id=task.task_id,
                    event_type=EventType.TASK_CREATED,
                    payload={
                        "title": task.title,
                        "priority": task.priority,
                        "engine": "OpenPlanter",
                        "depth": 1,
                    },
                )
            )
            created_tasks.append(task)

        return created_tasks

    def extract_search_queries(
        self,
        task: ResearchTask,
        objective_target: str = "",
        dork: bool | None = None,
    ) -> list[str]:
        """Extract search queries.

        Note: OpenPlanter generates direct OSINT queries without Argus's archetype-specific
        search dorking (newsroom/regulatory/directory site dorks) or System 1 classifier.
        """
        base_queries: list[str] = []
        if "Search Queries:" in task.description:
            parts = task.description.split("Search Queries:", 1)[1]
            lines = [line.strip() for line in parts.splitlines()]
            base_queries = [
                line[2:].strip()
                for line in lines
                if line.startswith("- ") and len(line) > 2
            ]

        if not base_queries:
            base_queries = [task.title]

        # OpenPlanter does not apply System 1 dorking; returns clean queries
        return base_queries[:4]

    def evaluate_stopping_criteria(
        self,
        objective: ResearchObjective,
        tasks_executed: int,
    ) -> StoppingEvaluation:
        """Evaluate stopping criteria.

        OpenPlanter uses task exhaustion and step budget rather than Argus's strict
        epistemic status verification. However, to interface with ArgusController,
        we compute field statuses from verified claims.
        """
        all_claims = self.repo.list_claims(objective_id=objective.objective_id)
        supported_claims = [
            c for c in all_claims
            if c.status in (ClaimStatus.SUPPORTED, ClaimStatus.CORROBORATED)
        ]

        # Compute field satisfaction
        missing_fields: list[str] = []
        field_statuses: dict[str, str] = {}

        for field in objective.required_fields:
            field_clean = field.strip().lower()
            matched = any(
                field_clean in c.predicate.lower() or field_clean in c.object_value.lower()
                for c in supported_claims
            )
            if matched:
                field_statuses[field] = "supported"
            else:
                field_statuses[field] = "not_found" if tasks_executed > 0 else "unknown"
                missing_fields.append(field)

        coverage = (
            (len(objective.required_fields) - len(missing_fields)) / len(objective.required_fields)
            if objective.required_fields
            else 1.0
        )

        # 1. Epistemic satisfaction check
        if len(missing_fields) == 0 and len(supported_claims) > 0:
            return StoppingEvaluation(
                should_stop=True,
                reason="OpenPlanter: All acceptance criteria and required fields verified.",
                missing_fields=[],
                coverage_score=1.0,
                field_statuses=field_statuses,
            )

        # 2. Budget safety limit
        if tasks_executed >= objective.max_tasks:
            return StoppingEvaluation(
                should_stop=True,
                reason=f"OpenPlanter: Max task budget reached ({tasks_executed}/{objective.max_tasks}).",
                missing_fields=missing_fields,
                coverage_score=coverage,
                field_statuses=field_statuses,
            )

        # In OpenPlanter, if ready tasks are exhausted and no followups exist, it stops
        ready_tasks = self.repo.list_tasks(
            objective_id=objective.objective_id,
            status=TaskStatus.READY,
        )
        if not ready_tasks and tasks_executed > 0 and len(missing_fields) == 0:
            return StoppingEvaluation(
                should_stop=True,
                reason="OpenPlanter: Investigation subtasks completed.",
                missing_fields=missing_fields,
                coverage_score=coverage,
                field_statuses=field_statuses,
            )

        return StoppingEvaluation(
            should_stop=False,
            reason=f"OpenPlanter: Investigating. Missing: {missing_fields}",
            missing_fields=missing_fields,
            coverage_score=coverage,
            field_statuses=field_statuses,
        )

    async def plan_followup_tasks(
        self,
        objective: ResearchObjective,
        missing_fields: list[str],
        disambiguation_tasks: list[str],
        parent_task: ResearchTask | None = None,
    ) -> list[ResearchTask]:
        """Recursive sub-agent delegation.

        Follows OpenPlanter's recursive subtask delegation up to max_depth (default 4).
        Note: Unlike Argus, OpenPlanter does not perform domain-specific facility fan-out
        or 3-attempt epistemic surrender.
        """
        new_depth = (parent_task.depth + 1) if parent_task else 1
        if new_depth > min(self.max_depth, objective.max_depth):
            return []

        existing_tasks = self.repo.list_tasks(objective_id=objective.objective_id)
        existing_titles = {t.title for t in existing_tasks}
        parent_id = parent_task.task_id if parent_task else None
        created_tasks: list[ResearchTask] = []

        # 1. Disambiguation tasks
        for query in disambiguation_tasks:
            title = f"Resolve contradiction: {query}"
            if title in existing_titles:
                continue

            desc = (
                f"Cross-reference sources to adjudicate conflicting findings: {query}\n\n"
                f"Acceptance Criteria: Consistent evidence chain established.\n\n"
                f"Search Queries:\n- {query}"
            )
            task = ResearchTask(
                objective_id=objective.objective_id,
                parent_task_id=parent_id,
                title=title,
                description=desc,
                status=TaskStatus.READY,
                priority=8,
                depth=new_depth,
            )
            self.repo.save_task(task)
            self.repo.record_event(
                ResearchEvent(
                    objective_id=objective.objective_id,
                    task_id=task.task_id,
                    event_type=EventType.TASK_CREATED,
                    payload={"title": title, "depth": new_depth, "engine": "OpenPlanter"},
                )
            )
            existing_titles.add(title)
            created_tasks.append(task)

        # 2. Missing fields recursion
        for field in missing_fields:
            title = f"Investigate {field} for {objective.target}"
            if title in existing_titles:
                continue

            query = f"{objective.target} {field}"
            desc = (
                f"Investigate unverified property '{field}' for target {objective.target}.\n\n"
                f"Acceptance Criteria: Grounded factual claim extracted for {field}.\n\n"
                f"Search Queries:\n- {query}"
            )
            task = ResearchTask(
                objective_id=objective.objective_id,
                parent_task_id=parent_id,
                title=title,
                description=desc,
                status=TaskStatus.READY,
                priority=6,
                depth=new_depth,
            )
            self.repo.save_task(task)
            self.repo.record_event(
                ResearchEvent(
                    objective_id=objective.objective_id,
                    task_id=task.task_id,
                    event_type=EventType.TASK_CREATED,
                    payload={"title": title, "depth": new_depth, "engine": "OpenPlanter"},
                )
            )
            existing_titles.add(title)
            created_tasks.append(task)

        return created_tasks

    async def synthesize_dossier(
        self,
        objective: ResearchObjective,
        total_tasks: int,
        total_documents: int,
    ) -> ResearchDossier:
        """Synthesize findings into an OpenPlanter evidence-backed briefing."""
        entities = self.repo.list_entities(objective_id=objective.objective_id)
        claims = self.repo.list_claims(objective_id=objective.objective_id)

        entity_summaries: list[DossierEntitySummary] = []
        for ent in entities:
            ent_claims = [c for c in claims if c.subject_entity_id == ent.entity_id]
            entity_summaries.append(
                DossierEntitySummary(
                    entity=ent,
                    supported_claims=[c for c in ent_claims if c.status == ClaimStatus.SUPPORTED],
                    corroborated_claims=[c for c in ent_claims if c.status == ClaimStatus.CORROBORATED],
                    inferred_claims=[c for c in ent_claims if c.status == ClaimStatus.INFERRED],
                    unverified_claims=[c for c in ent_claims if c.status == ClaimStatus.UNVERIFIED],
                    contradicted_claims=[c for c in ent_claims if c.status == ClaimStatus.CONTRADICTED],
                )
            )

        stopping_eval = self.evaluate_stopping_criteria(
            objective=objective, tasks_executed=total_tasks
        )

        unresolved = sum(
            1 for c in claims if c.status == ClaimStatus.CONTRADICTED
        )

        return ResearchDossier(
            objective_id=objective.objective_id,
            target=objective.target,
            intelligence_goal=objective.intelligence_goal,
            executive_summary=(
                f"OpenPlanter autonomous OSINT dossier for {objective.target}. "
                f"Identified {len(entities)} entities with {len(claims)} evaluated claims. "
                f"Epistemic coverage achieved: {stopping_eval.coverage_score:.1%}."
            ),
            entities=entity_summaries,
            total_tasks_executed=total_tasks,
            total_documents_crawled=total_documents,
            unresolved_contradictions=unresolved,
            coverage_achieved=stopping_eval.coverage_score,
            field_statuses=stopping_eval.field_statuses,
        )
