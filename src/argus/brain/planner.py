import asyncio
import re
from typing import Any

from argus.brain.models import (
    DossierEntitySummary,
    ResearchDossier,
    StoppingEvaluation,
    SynthesisPayload,
    TaskPlanningPayload,
)
from argus.brain.prompts import (
    PLANNER_SYSTEM_PROMPT,
    build_decomposition_prompt,
    build_synthesis_prompt,
)
from argus.brain.base import BaseResearchBrain
from argus.domain.claim import Claim, ClaimStatus
from argus.domain.event import EventType, ResearchEvent
from argus.domain.objective import ResearchObjective
from argus.domain.task import ResearchTask, TaskStatus
from argus.llm.provider import LLMProvider
from argus.storage.repository import ArgusRepository


class ResearchBrain(BaseResearchBrain):
    """Strategic executive planner for objective decomposition, epistemic stopping, and dossier synthesis."""

    def __init__(
        self, repo: ArgusRepository, llm: LLMProvider, system1: Any = None
    ) -> None:
        self.repo = repo
        self.llm = llm
        self.system1 = system1

    async def plan_initial_tasks(
        self, objective: ResearchObjective
    ) -> list[ResearchTask]:
        """Decompose a ResearchObjective into initial executable tasks."""
        prompt = build_decomposition_prompt(
            target=objective.target,
            target_type=objective.target_type,
            intelligence_goal=objective.intelligence_goal,
            required_fields=objective.required_fields,
            success_criteria=objective.success_criteria,
        )

        payload: TaskPlanningPayload = await self.llm.generate_structured(
            prompt=prompt,
            response_model=TaskPlanningPayload,
            system_prompt=PLANNER_SYSTEM_PROMPT,
        )

        created_tasks: list[ResearchTask] = []
        for planned in payload.planned_tasks:
            desc = planned.description
            if planned.search_queries:
                queries_text = "\n".join(f"- {q}" for q in planned.search_queries)
                desc = f"{desc}\n\nSearch Queries:\n{queries_text}"

            priority = planned.priority
            if self.system1 is not None and hasattr(self.system1, "score_task_priority"):
                priority = self.system1.score_task_priority(
                    task_title=planned.title,
                    task_description=desc,
                    objective_goal=objective.intelligence_goal,
                    required_fields=objective.required_fields,
                )

            task = ResearchTask(
                objective_id=objective.objective_id,
                title=planned.title,
                description=desc,
                status=TaskStatus.READY,
                priority=priority,
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
                        "search_queries": planned.search_queries,
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
        """Parse search queries and optionally apply dynamic archetype search dorking."""
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

        should_dork = dork if dork is not None else (self.system1 is not None)
        if not should_dork:
            return base_queries

        # Determine archetype via System 1 (with heuristic fallback)
        if self.system1 is not None:
            archetype = self.system1.classify_search_archetype(
                task_title=task.title,
                task_description=task.description,
                objective_target=objective_target,
            )
        else:
            from argus.brain.system1 import System1DecisionEngine

            archetype = System1DecisionEngine.infer_archetype_heuristic(
                f"{task.title} {task.description} {objective_target}"
            )

        return self._generate_archetype_dorks(
            base_queries=base_queries,
            archetype=archetype,
            target=objective_target,
        )

    def _generate_archetype_dorks(
        self,
        base_queries: list[str],
        archetype: str,
        target: str = "",
        max_queries: int = 4,
    ) -> list[str]:
        """Generate high-yield search dorks tailored to information source archetype."""
        generated: list[str] = []

        for q in base_queries:
            q_clean = q.strip()
            if not q_clean:
                continue
            generated.append(q_clean)

            if archetype == "newsroom":
                if "site:linkedin.com" not in q_clean:
                    generated.append(f"{q_clean} site:linkedin.com/in")
                generated.append(
                    f'{q_clean} ("appointed" OR "named" OR "promoted" OR "press release")'
                )
                if target and target.lower() not in q_clean.lower():
                    generated.append(f'"{target}" {q_clean} executive appointment')

            elif archetype == "regulatory":
                if "site:gov" not in q_clean:
                    generated.append(
                        f'{q_clean} site:gov ("permit" OR "compliance" OR "inspection" OR "violation")'
                    )
                generated.append(
                    f'{q_clean} ("regulatory filing" OR "inspection report" OR "compliance audit")'
                )

            elif archetype == "directory":
                generated.append(
                    f'{q_clean} ("facility directory" OR "locations" OR "address" OR "switchboard" OR "contact")'
                )
                generated.append(
                    f'{q_clean} ("supplier registry" OR "operations directory" OR "site list")'
                )

            elif archetype == "technical":
                generated.append(
                    f'{q_clean} ("specification" OR "whitepaper" OR "datasheet" OR "patent")'
                )

        # Deduplicate while preserving order
        unique_queries: list[str] = []
        seen: set[str] = set()
        for g in generated:
            g_norm = " ".join(g.split()).lower()
            if g_norm not in seen:
                seen.add(g_norm)
                unique_queries.append(g)

        return unique_queries[:max_queries]

    def _is_field_satisfied(
        self, field_name: str, supported_claims: list[Claim]
    ) -> bool:
        """Check if a required field is satisfied using dynamic token matching.

        Completely domain-agnostic: works across any domain or industry without static wordlists.
        """
        fn_clean = field_name.strip().lower()
        fn_tokens = {tok for tok in re.split(r"[^a-zA-Z0-9]+", fn_clean) if len(tok) > 1}

        for claim in supported_claims:
            pred_lower = claim.predicate.lower()
            obj_lower = claim.object_value.lower()
            claim_text = f"{pred_lower} {obj_lower}"
            claim_tokens = {tok for tok in re.split(r"[^a-zA-Z0-9]+", claim_text) if len(tok) > 1}

            # 1. Exact or normalized substring match
            if fn_clean in pred_lower or fn_clean in obj_lower:
                return True
            if fn_clean.replace("_", "") in pred_lower.replace("_", ""):
                return True

            # 2. Complete token containment
            if fn_tokens and fn_tokens.issubset(claim_tokens):
                return True

            # 3. Dynamic token overlap (50%+ token overlap for compound fields)
            if fn_tokens and len(fn_tokens & claim_tokens) >= max(1, len(fn_tokens) // 2 + 1):
                return True

        return False

    def evaluate_stopping_criteria(
        self,
        objective: ResearchObjective,
        tasks_executed: int,
    ) -> StoppingEvaluation:
        """Evaluate if research should terminate based on budget or epistemic satisfaction."""
        # 1. Epistemic requirement satisfaction (compute true coverage first)
        verified_claims = self.repo.list_claims(
            objective_id=objective.objective_id,
            status=[ClaimStatus.SUPPORTED, ClaimStatus.CORROBORATED],
        )
        all_claims = self.repo.list_claims(objective_id=objective.objective_id)

        corroborated_claims = [c for c in all_claims if c.status == ClaimStatus.CORROBORATED]
        supported_claims = [c for c in all_claims if c.status == ClaimStatus.SUPPORTED]
        inferred_claims = [c for c in all_claims if c.status == ClaimStatus.INFERRED]
        contradicted_claims = [c for c in all_claims if c.status == ClaimStatus.CONTRADICTED]
        unverified_claims = [c for c in all_claims if c.status == ClaimStatus.UNVERIFIED]

        missing_fields: list[str] = []
        field_statuses: dict[str, str] = {}

        for field_name in objective.required_fields:
            if self._is_field_satisfied(field_name, corroborated_claims):
                field_statuses[field_name] = "corroborated"
            elif self._is_field_satisfied(field_name, supported_claims):
                field_statuses[field_name] = "supported"
            elif self._is_field_satisfied(field_name, inferred_claims):
                field_statuses[field_name] = "inferred"
                missing_fields.append(field_name)
            elif self._is_field_satisfied(field_name, contradicted_claims):
                field_statuses[field_name] = "contradicted"
                missing_fields.append(field_name)
            elif self._is_field_satisfied(field_name, unverified_claims):
                field_statuses[field_name] = "unverified"
                missing_fields.append(field_name)
            else:
                field_statuses[field_name] = "not_found" if tasks_executed > 0 else "unknown"
                missing_fields.append(field_name)

        if not objective.required_fields:
            coverage = 1.0
        else:
            coverage = (len(objective.required_fields) - len(missing_fields)) / len(
                objective.required_fields
            )

        # 2. Epistemic satisfaction check (only verified claims satisfy stopping criteria)
        if len(missing_fields) == 0 and len(verified_claims) > 0:
            return StoppingEvaluation(
                should_stop=True,
                reason="All required fields satisfied with verified evidence.",
                missing_fields=[],
                coverage_score=1.0,
                field_statuses=field_statuses,
            )

        # 3. Budget safety boundary check (preserves true coverage and real missing fields)
        if tasks_executed >= objective.max_tasks:
            return StoppingEvaluation(
                should_stop=True,
                reason=(
                    f"Task execution budget reached ({tasks_executed}/{objective.max_tasks}). "
                    f"Epistemic coverage at {coverage:.0%}. Missing: {missing_fields}"
                ),
                missing_fields=missing_fields,
                coverage_score=coverage,
                field_statuses=field_statuses,
            )

        return StoppingEvaluation(
            should_stop=False,
            reason=f"Epistemic coverage at {coverage:.0%}. Missing: {missing_fields}",
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
        """Create targeted follow-up tasks for missing fields or contradictions.

        Enforces recursion max_depth and prevents repetitive task spam on unresolvable fields.
        """
        # Enforce tree depth recursion limit
        new_depth = (parent_task.depth + 1) if parent_task else 1
        if new_depth > objective.max_depth:
            return []

        # Prevent repetitive task spam on unresolvable fields and duplicate disambiguation
        existing_tasks = self.repo.list_tasks(objective_id=objective.objective_id)
        existing_titles = {t.title for t in existing_tasks}

        created_tasks: list[ResearchTask] = []
        parent_id = parent_task.task_id if parent_task else None

        # Disambiguation tasks: score priority dynamically via Laya System 1 or heuristic
        for query in disambiguation_tasks:
            title = f"Disambiguate: {query}"
            if title in existing_titles:
                continue

            desc = f"Resolve factual contradiction: {query}\n\nSearch Queries:\n- {query}"

            # Dynamic branch depth gating: check if branch should recurse deeper
            if self.system1 is not None and hasattr(self.system1, "should_branch_deeper"):
                if not self.system1.should_branch_deeper(
                    task_title=title,
                    task_description=desc,
                    current_depth=new_depth,
                    max_depth=objective.max_depth,
                    objective_goal=objective.intelligence_goal,
                ):
                    continue
            else:
                from argus.brain.system1 import System1DecisionEngine

                if not System1DecisionEngine.infer_branch_depth_heuristic(
                    task_title=title,
                    task_description=desc,
                    current_depth=new_depth,
                    max_depth=objective.max_depth,
                ):
                    continue

            if self.system1 is not None and hasattr(self.system1, "score_task_priority"):
                priority = self.system1.score_task_priority(
                    task_title=title,
                    task_description=desc,
                    objective_goal=objective.intelligence_goal,
                    required_fields=objective.required_fields,
                )
            else:
                from argus.brain.system1 import System1DecisionEngine

                priority = System1DecisionEngine.infer_priority_heuristic(
                    title, desc, objective.required_fields
                )

            task = ResearchTask(
                objective_id=objective.objective_id,
                parent_task_id=parent_id,
                title=title,
                description=desc,
                status=TaskStatus.READY,
                priority=priority,
                depth=new_depth,
            )
            self.repo.save_task(task)
            self.repo.record_event(
                ResearchEvent(
                    objective_id=objective.objective_id,
                    task_id=task.task_id,
                    event_type=EventType.TASK_CREATED,
                    payload={
                        "title": task.title,
                        "depth": task.depth,
                        "priority": task.priority,
                        "type": "disambiguation",
                    },
                )
            )
            existing_titles.add(title)
            created_tasks.append(task)

        # Check if missing_fields includes facility-level personnel/leadership/contact requirements
        facility_fields = {
            "plant_head", "plant_manager", "tech_lead", "contact_info",
            "director", "manager", "lead", "leadership", "plant",
        }
        has_facility_field_missing = any(
            any(ff in mf.lower() for ff in facility_fields)
            for mf in missing_fields
        )

        entities = self.repo.list_entities(objective_id=objective.objective_id)
        facility_types = {
            "facility", "manufacturing_plant", "assembly_plant", "plant",
            "manufacturing_facility", "battery_manufacturing_plant", "factory",
            "operations", "metal_center", "casting",
        }
        facilities = [e for e in entities if e.entity_type.lower() in facility_types]

        # 1. FAN-OUT: If facilities are discovered and leadership/contacts are missing,
        # probe EACH plant individually rather than querying the entire industry as 1 lump.
        if has_facility_field_missing and facilities:
            supported_claims = self.repo.list_claims(
                objective_id=objective.objective_id,
                status=[ClaimStatus.SUPPORTED, ClaimStatus.CORROBORATED],
            )
            plants_with_leadership = set()
            for c in supported_claims:
                pred = c.predicate.upper()
                if pred in ("HAS_PLANT_MANAGER", "DIRECTED_BY", "HAS_HEAD", "PLANT_DIRECTOR"):
                    plants_with_leadership.add(c.subject_entity_id)
                elif pred in ("IS_PLANT_MANAGER_OF", "DIRECTOR_OF", "MANAGES") and c.object_entity_id:
                    plants_with_leadership.add(c.object_entity_id)

            for fac in facilities:
                if len(existing_tasks) + len(created_tasks) >= objective.max_tasks:
                    break

                if fac.entity_id in plants_with_leadership:
                    continue

                fac_title = f"Investigate leadership and contacts for {fac.canonical_name}"
                if fac_title in existing_titles:
                    continue

                fac_desc = (
                    f"Find verified plant director, site leadership, engineering leads, and contact switchboard for {fac.canonical_name}.\n\n"
                    f"Search Queries:\n"
                    f"- \"{fac.canonical_name}\" plant manager OR director\n"
                    f"- \"{fac.canonical_name}\" site:linkedin.com/in (\"plant manager\" OR \"director\" OR \"operations\")\n"
                    f"- \"{fac.canonical_name}\" plant director appointed OR leadership\n"
                    f"- \"{fac.canonical_name}\" engineering lead OR chief engineer\n"
                    f"- \"{fac.canonical_name}\" contact phone switchboard"
                )

                if self.system1 is not None and hasattr(self.system1, "should_branch_deeper"):
                    if not self.system1.should_branch_deeper(
                        task_title=fac_title,
                        task_description=fac_desc,
                        current_depth=new_depth,
                        max_depth=objective.max_depth,
                        objective_goal=objective.intelligence_goal,
                    ):
                        continue
                else:
                    from argus.brain.system1 import System1DecisionEngine

                    if not System1DecisionEngine.infer_branch_depth_heuristic(
                        task_title=fac_title,
                        task_description=fac_desc,
                        current_depth=new_depth,
                        max_depth=objective.max_depth,
                    ):
                        continue

                if self.system1 is not None and hasattr(self.system1, "score_task_priority"):
                    priority = self.system1.score_task_priority(
                        task_title=fac_title,
                        task_description=fac_desc,
                        objective_goal=objective.intelligence_goal,
                        required_fields=objective.required_fields,
                    )
                else:
                    from argus.brain.system1 import System1DecisionEngine

                    priority = System1DecisionEngine.infer_priority_heuristic(
                        fac_title, fac_desc, objective.required_fields
                    )

                task = ResearchTask(
                    objective_id=objective.objective_id,
                    parent_task_id=parent_id,
                    title=fac_title,
                    description=fac_desc,
                    status=TaskStatus.READY,
                    priority=priority,
                    depth=new_depth,
                )
                self.repo.save_task(task)
                self.repo.record_event(
                    ResearchEvent(
                        objective_id=objective.objective_id,
                        task_id=task.task_id,
                        event_type=EventType.TASK_CREATED,
                        payload={
                            "title": task.title,
                            "depth": task.depth,
                            "priority": task.priority,
                            "type": "plant_individual_probing",
                            "facility": fac.canonical_name,
                        },
                    )
                )
                existing_titles.add(fac_title)
                created_tasks.append(task)

        # 2. Targeted tasks for remaining missing fields: score priority dynamically via Laya System 1 or heuristic
        for field in missing_fields:
            if has_facility_field_missing and facilities and any(ff in field.lower() for ff in facility_fields):
                continue

            title = f"Investigate {field} for {objective.target}"
            if title in existing_titles:
                continue
            
            # Pain Point 8: Epistemic Surrender (Ghost Target Infinite Loops)
            # If we've already tried to investigate this specific field 3+ times across the task tree,
            # surrender and prune the branch to prevent budget bloat.
            field_attempts = sum(1 for t in existing_tasks if t.title == title)
            if field_attempts >= 3:
                continue

            query = f"{objective.target} {field}"
            desc = f"Find verified information regarding {field}.\n\nSearch Queries:\n- {query}"

            # Dynamic branch depth gating: check if branch should recurse deeper
            if self.system1 is not None and hasattr(self.system1, "should_branch_deeper"):
                if not self.system1.should_branch_deeper(
                    task_title=title,
                    task_description=desc,
                    current_depth=new_depth,
                    max_depth=objective.max_depth,
                    objective_goal=objective.intelligence_goal,
                ):
                    continue
            else:
                from argus.brain.system1 import System1DecisionEngine

                if not System1DecisionEngine.infer_branch_depth_heuristic(
                    task_title=title,
                    task_description=desc,
                    current_depth=new_depth,
                    max_depth=objective.max_depth,
                ):
                    continue

            if self.system1 is not None and hasattr(self.system1, "score_task_priority"):
                priority = self.system1.score_task_priority(
                    task_title=title,
                    task_description=desc,
                    objective_goal=objective.intelligence_goal,
                    required_fields=objective.required_fields,
                )
            else:
                from argus.brain.system1 import System1DecisionEngine

                priority = System1DecisionEngine.infer_priority_heuristic(
                    title, desc, objective.required_fields
                )

            task = ResearchTask(
                objective_id=objective.objective_id,
                parent_task_id=parent_id,
                title=title,
                description=desc,
                status=TaskStatus.READY,
                priority=priority,
                depth=new_depth,
            )
            self.repo.save_task(task)
            self.repo.record_event(
                ResearchEvent(
                    objective_id=objective.objective_id,
                    task_id=task.task_id,
                    event_type=EventType.TASK_CREATED,
                    payload={
                        "title": task.title,
                        "depth": task.depth,
                        "priority": task.priority,
                        "type": "missing_field",
                    },
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
        """Synthesize all verified evidence into a final ResearchDossier."""
        entities = self.repo.list_entities(objective_id=objective.objective_id)
        all_claims = self.repo.list_claims(objective_id=objective.objective_id)

        supported_map: dict[str, list[Claim]] = {}
        corroborated_map: dict[str, list[Claim]] = {}
        inferred_map: dict[str, list[Claim]] = {}
        unverified_map: dict[str, list[Claim]] = {}
        contradicted_map: dict[str, list[Claim]] = {}
        unresolved_contradictions = 0

        for c in all_claims:
            if c.status == ClaimStatus.CORROBORATED:
                corroborated_map.setdefault(c.subject_entity_id, []).append(c)
            elif c.status == ClaimStatus.SUPPORTED:
                supported_map.setdefault(c.subject_entity_id, []).append(c)
            elif c.status == ClaimStatus.INFERRED:
                inferred_map.setdefault(c.subject_entity_id, []).append(c)
            elif c.status == ClaimStatus.UNVERIFIED:
                unverified_map.setdefault(c.subject_entity_id, []).append(c)
            elif c.status == ClaimStatus.CONTRADICTED:
                contradicted_map.setdefault(c.subject_entity_id, []).append(c)
                unresolved_contradictions += 1

        entity_summaries: list[DossierEntitySummary] = []
        for ent in entities:
            entity_summaries.append(
                DossierEntitySummary(
                    entity=ent,
                    supported_claims=supported_map.get(ent.entity_id, []),
                    corroborated_claims=corroborated_map.get(ent.entity_id, []),
                    inferred_claims=inferred_map.get(ent.entity_id, []),
                    unverified_claims=unverified_map.get(ent.entity_id, []),
                    contradicted_claims=contradicted_map.get(ent.entity_id, []),
                )
            )

        stopping_eval = self.evaluate_stopping_criteria(
            objective, tasks_executed=total_tasks
        )

        # Hierarchical Map-Reduce Synthesis if claims are too large
        if len(all_claims) > 50:
            entity_summaries_text = []
            for ent_summary in entity_summaries:
                ent_name = ent_summary.entity.canonical_name
                parts = []
                if ent_summary.corroborated_claims:
                    c_text = ", ".join(f"{c.predicate}: {c.object_value} [CORROBORATED]" for c in ent_summary.corroborated_claims)
                    parts.append(c_text)
                if ent_summary.supported_claims:
                    s_text = ", ".join(f"{c.predicate}: {c.object_value}" for c in ent_summary.supported_claims)
                    parts.append(s_text)
                if ent_summary.inferred_claims:
                    i_text = ", ".join(f"{c.predicate}: {c.object_value} [INFERRED via {c.derivation_method or 'derivation'}]" for c in ent_summary.inferred_claims)
                    parts.append(i_text)
                if ent_summary.contradicted_claims:
                    d_text = ", ".join(f"{c.predicate}: {c.object_value} [DISPUTED]" for c in ent_summary.contradicted_claims)
                    parts.append(d_text)
                if parts:
                    entity_summaries_text.append(f"{ent_name}: {'; '.join(parts)}")

            supported_claims_text = "MAP-REDUCE ENTITY SUMMARIES:\n" + "\n".join(entity_summaries_text[:100])
            corroborated_claims_text = "Included in entity summaries above."
            inferred_claims_text = "Included in entity summaries above."
            unverified_claims_text = "Included in entity summaries above."
            contradictions_text = "See entity summaries."
        else:
            supported_lines = [
                f"- {c.predicate}: {c.object_value} (confidence: {c.confidence})"
                for c in all_claims
                if c.status == ClaimStatus.SUPPORTED
            ]
            corroborated_lines = [
                f"- {c.predicate}: {c.object_value} (multi-source verified)"
                for c in all_claims
                if c.status == ClaimStatus.CORROBORATED
            ]
            inferred_lines = [
                f"- {c.predicate}: {c.object_value} (INFERRED via {c.derivation_method or 'derivation'}; reason: {c.inference_reason or 'derived pattern'})"
                for c in all_claims
                if c.status == ClaimStatus.INFERRED
            ]
            unverified_lines = [
                f"- {c.predicate}: {c.object_value} (confidence: {c.confidence}) [UNVERIFIED]"
                for c in all_claims
                if c.status == ClaimStatus.UNVERIFIED
            ]
            contradicted_lines = [
                f"- {c.predicate}: {c.object_value} [DISPUTED]"
                for c in all_claims
                if c.status == ClaimStatus.CONTRADICTED
            ]
            supported_claims_text = "\n".join(supported_lines)
            corroborated_claims_text = "\n".join(corroborated_lines)
            inferred_claims_text = "\n".join(inferred_lines)
            unverified_claims_text = "\n".join(unverified_lines)
            contradictions_text = "\n".join(contradicted_lines)

        not_found_lines = [
            f"- {field}: Not found in public records"
            for field, st in stopping_eval.field_statuses.items()
            if st in ("not_found", "unknown")
        ]
        not_found_text = "\n".join(not_found_lines)

        prompt = build_synthesis_prompt(
            target=objective.target,
            intelligence_goal=objective.intelligence_goal,
            entities_count=len(entities),
            supported_claims_text=supported_claims_text,
            contradictions_text=contradictions_text,
            corroborated_claims_text=corroborated_claims_text,
            inferred_claims_text=inferred_claims_text,
            unverified_claims_text=unverified_claims_text,
            not_found_text=not_found_text,
        )

        try:
            payload: SynthesisPayload = await self.llm.generate_structured(
                prompt=prompt,
                response_model=SynthesisPayload,
                system_prompt=PLANNER_SYSTEM_PROMPT,
            )
            exec_summary = payload.executive_summary
        except (ValueError, KeyError, RuntimeError, TypeError):
            verified_count = len([c for c in all_claims if c.status in (ClaimStatus.SUPPORTED, ClaimStatus.CORROBORATED)])
            inferred_count = len([c for c in all_claims if c.status == ClaimStatus.INFERRED])
            contradicted_count = len([c for c in all_claims if c.status == ClaimStatus.CONTRADICTED])
            summary_parts = [
                f"Autonomous investigation on {objective.target} concluded. ",
                f"Discovered {len(entities)} entities with {verified_count} verified claims",
            ]
            if inferred_count > 0:
                summary_parts.append(f", {inferred_count} inferred values (unverified derivations)")
            if contradicted_count > 0:
                summary_parts.append(f", and {contradicted_count} disputed contradictions")
            summary_parts.append(".")
            if stopping_eval.missing_fields:
                summary_parts.append(f" Fields not found: {', '.join(stopping_eval.missing_fields)}.")
            exec_summary = "".join(summary_parts)

        return ResearchDossier(
            objective_id=objective.objective_id,
            target=objective.target,
            intelligence_goal=objective.intelligence_goal,
            executive_summary=exec_summary,
            entities=entity_summaries,
            total_tasks_executed=total_tasks,
            total_documents_crawled=total_documents,
            unresolved_contradictions=unresolved_contradictions,
            coverage_achieved=stopping_eval.coverage_score,
            field_statuses=stopping_eval.field_statuses,
        )


# Alias for explicit architecture contract
ArgusBrain = ResearchBrain
