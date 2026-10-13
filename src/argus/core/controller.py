import logging
import os

from argus.brain.models import ResearchDossier
from argus.brain.planner import ResearchBrain
from argus.brain.system1 import System1DecisionEngine
from argus.contact.resolver import ContactResolutionEngine
from argus.core.state_machine import TaskStateMachine
from argus.crawler.engine import CrawlExecutionEngine
from argus.crawler.fetcher import TwoTierFetcher
from argus.crawler.mock import MockFetcher
from argus.crawler.models import CrawlRequest
from argus.domain.claim import ClaimStatus
from argus.domain.event import EventType, ResearchEvent
from argus.domain.objective import ResearchObjective
from argus.domain.stage import ResearchStage
from argus.domain.task import TaskStatus
from argus.search.models import SearchQuery
from argus.search.pipeline import SearchPipeline
from argus.storage.repository import ArgusRepository
from argus.verifier.engine import ExpertVerifier
from argus.worker.engine import WorkerEngine

logger = logging.getLogger(__name__)


class ArgusController:
    """The central orchestrator driving autonomous multi-turn research loops."""

    def __init__(
        self,
        repo: ArgusRepository,
        search_pipeline: SearchPipeline,
        fetcher: TwoTierFetcher | MockFetcher,
        worker: WorkerEngine,
        verifier: ExpertVerifier,
        brain: ResearchBrain,
        system1: System1DecisionEngine | None = None,
        contact_resolver: ContactResolutionEngine | None = None,
        crawl_engine: CrawlExecutionEngine | None = None,
    ) -> None:
        self.repo = repo
        self.search_pipeline = search_pipeline
        self.fetcher = fetcher
        self.worker = worker
        self.verifier = verifier
        self.brain = brain
        self.system1 = system1
        self.contact_resolver = contact_resolver
        self.crawl_engine = crawl_engine or CrawlExecutionEngine(
            fetcher=self.fetcher,
            repo=self.repo,
            memory_storage=True if isinstance(self.fetcher, MockFetcher) else False,
        )
        if self.system1 is not None and getattr(self.brain, "system1", None) is None:
            self.brain.system1 = self.system1

    async def run(
        self,
        objective: ResearchObjective,
        max_crawl_pages_per_task: int = 3,
    ) -> ResearchDossier:
        """Execute a complete autonomous research investigation for an objective."""
        # 1. Dynamic calibration of task budget & depth via Laya System 1 (if enabled)
        if (
            getattr(objective, "dynamic_budget", True)
            and self.system1 is not None
            and hasattr(self.system1, "calibrate_budget_and_depth")
        ):
            calibrated_tasks, calibrated_depth = self.system1.calibrate_budget_and_depth(
                objective_target=objective.target,
                intelligence_goal=objective.intelligence_goal,
                required_fields=objective.required_fields,
            )
            objective.max_tasks = calibrated_tasks
            objective.max_depth = calibrated_depth
            logger.info(
                "Laya dynamically calibrated budget for %s: max_tasks=%d, max_depth=%d",
                objective.target,
                calibrated_tasks,
                calibrated_depth,
            )

        # 2. Lifecycle start: purge any legacy matrix records for 100% autonomous run
        if hasattr(self.repo, "purge_plant_leadership_matrix"):
            self.repo.purge_plant_leadership_matrix()

        self.repo.save_objective(objective)
        self.repo.record_event(
            ResearchEvent(
                objective_id=objective.objective_id,
                event_type=EventType.RESEARCH_STARTED,
                payload={
                    "target": objective.target,
                    "goal": objective.intelligence_goal,
                    "max_tasks": objective.max_tasks,
                    "max_depth": objective.max_depth,
                },
            )
        )

        current_stage = ResearchStage.RECONNAISSANCE
        self.repo.record_event(
            ResearchEvent(
                objective_id=objective.objective_id,
                event_type=EventType.STAGE_STARTED,
                payload={"stage": current_stage.value},
            )
        )

        # 2. Decompose into initial tasks
        await self.brain.plan_initial_tasks(objective)

        tasks_executed = 0
        documents_crawled = 0
        consecutive_zero_yield_tasks = 0
        crawled_urls = self.repo.get_crawled_urls()
        stop_reason = ""

        # 3. Main Orchestration Loop
        while True:
            # Check stopping criteria
            stopping_eval = self.brain.evaluate_stopping_criteria(
                objective=objective,
                tasks_executed=tasks_executed,
            )
            if stopping_eval.should_stop:
                stop_reason = stopping_eval.reason
                break

            # Diminishing returns detection: 3 consecutive zero-yield tasks
            if consecutive_zero_yield_tasks >= 3:
                # If facilities were discovered but not yet probed for leadership, switch to plant fan-out rather than halting
                facility_types = {
                    "facility", "manufacturing_plant", "assembly_plant", "plant",
                    "manufacturing_facility", "battery_manufacturing_plant", "factory",
                    "operations", "metal_center", "casting",
                }
                facilities = [
                    e for e in self.repo.list_entities(objective_id=objective.objective_id)
                    if e.entity_type.lower() in facility_types
                ]
                existing_tasks = self.repo.list_tasks(objective_id=objective.objective_id)
                has_plant_tasks = any(
                    "Investigate leadership and contacts for" in t.title
                    for t in existing_tasks
                )
                if (
                    facilities
                    and not has_plant_tasks
                    and tasks_executed < objective.max_tasks
                ):
                    current_stage = ResearchStage.PERSONNEL_LEADERSHIP
                    consecutive_zero_yield_tasks = 0
                    await self.brain.plan_followup_tasks(
                        objective=objective,
                        missing_fields=["plant_head", "tech_lead", "contact_info"],
                        disambiguation_tasks=[],
                    )
                    ready_tasks = self.repo.list_tasks(
                        objective_id=objective.objective_id,
                        status=TaskStatus.READY,
                    )
                    if ready_tasks:
                        continue

                stop_reason = (
                    "diminishing_returns: 3 consecutive tasks produced zero new supported claims"
                )
                break

            # Progressively advance stages based on evidence maturity
            current_stage = self._transition_stage_if_needed(
                objective=objective,
                current_stage=current_stage,
                tasks_executed=tasks_executed,
            )

            # Proactive fan-out: When in Personnel & Leadership stage, ensure plant-level tasks are scheduled
            if current_stage == ResearchStage.PERSONNEL_LEADERSHIP:
                facility_types = {
                    "facility", "manufacturing_plant", "assembly_plant", "plant",
                    "manufacturing_facility", "battery_manufacturing_plant", "factory",
                    "operations", "metal_center", "casting",
                }
                facilities = [
                    e for e in self.repo.list_entities(objective_id=objective.objective_id)
                    if e.entity_type.lower() in facility_types
                ]
                existing_tasks = self.repo.list_tasks(objective_id=objective.objective_id)
                has_plant_probing_tasks = any(
                    "Investigate leadership and contacts for" in t.title
                    for t in existing_tasks
                )
                if facilities and not has_plant_probing_tasks:
                    await self.brain.plan_followup_tasks(
                        objective=objective,
                        missing_fields=["plant_head", "tech_lead", "contact_info"],
                        disambiguation_tasks=[],
                    )

            # Retrieve next ready task
            ready_tasks = self.repo.list_tasks(
                objective_id=objective.objective_id,
                status=TaskStatus.READY,
            )

            if not ready_tasks:
                if stopping_eval.missing_fields:
                    followups = await self.brain.plan_followup_tasks(
                        objective=objective,
                        missing_fields=stopping_eval.missing_fields,
                        disambiguation_tasks=[],
                    )
                    if not followups:
                        break
                    continue
                else:
                    break

            current_task = ready_tasks[0]

            # Transition task to RUNNING
            TaskStateMachine.transition(current_task, TaskStatus.RUNNING)
            self.repo.save_task(current_task)
            self.repo.record_event(
                ResearchEvent(
                    objective_id=objective.objective_id,
                    task_id=current_task.task_id,
                    event_type=EventType.TASK_STARTED,
                    payload={"title": current_task.title, "stage": current_stage.value},
                )
            )

            # Measure supported/corroborated claims baseline before execution
            supported_before = len(
                self.repo.list_claims(
                    objective_id=objective.objective_id,
                    status=[ClaimStatus.SUPPORTED, ClaimStatus.CORROBORATED],
                )
            )

            try:
                # Extract and dispatch search queries
                queries = self.brain.extract_search_queries(
                    current_task,
                    objective_target=objective.target,
                    dork=True if self.system1 is not None else False,
                )
                discovered_urls: list[str] = []

                for query_str in queries:
                    # Request broader candidate pool so System 1 can triage and rank
                    num_fetch = max(max_crawl_pages_per_task * 2, 6)
                    search_resp = await self.search_pipeline.search(
                        SearchQuery(
                            query=query_str, num_results=num_fetch
                        )
                    )
                    self.repo.record_event(
                        ResearchEvent(
                            objective_id=objective.objective_id,
                            task_id=current_task.task_id,
                            event_type=EventType.SEARCH_EXECUTED,
                            payload={
                                "query": query_str,
                                "results_found": len(search_resp.results),
                            },
                        )
                    )

                    # System 1 Snippet Triage (Laya ~33ms non-autoregressive ranking)
                    if self.system1 is not None:
                        triaged_items = self.system1.triage_search_results(
                            results=search_resp.results,
                            objective_target=objective.target,
                            task_title=current_task.title,
                            top_k=max_crawl_pages_per_task,
                        )
                    else:
                        triaged_items = search_resp.results

                    for item in triaged_items:
                        normalized_url = self.search_pipeline.normalize_url(item.url)
                        if (
                            normalized_url not in discovered_urls
                            and normalized_url not in crawled_urls
                        ):
                            discovered_urls.append(normalized_url)

                # Enqueue triaged candidate URLs to persistent Crawlee RequestQueue
                target_urls = [
                    u for u in discovered_urls[:max_crawl_pages_per_task]
                    if u not in crawled_urls
                ]
                await self.crawl_engine.enqueue_urls(
                    urls=target_urls,
                    objective_id=objective.objective_id,
                    task_id=current_task.task_id,
                    priority=current_task.priority,
                )

                # Process next batch from Crawlee queue (HTTP-first -> Playwright browser fallback)
                batch_docs = await self.crawl_engine.process_next_batch(
                    objective_id=objective.objective_id,
                    max_pages=max_crawl_pages_per_task,
                    task_id=current_task.task_id,
                )

                # Dispatch worker extraction and downstream processing
                for doc in batch_docs:
                    crawled_urls.add(doc.url)
                    if doc.url:
                        crawled_urls.add(self.search_pipeline.normalize_url(doc.url))

                    if doc.status_code == 200 and len(doc.text_content) > 20:
                        # System 1 Document Noise Filter (Laya ~33ms fast gatekeeper)
                        if self.system1 is not None:
                            is_rel, conf, cat = self.system1.triage_document(
                                doc_text=doc.text_content,
                                task_title=current_task.title,
                                objective_target=objective.target,
                            )
                            if not is_rel:
                                continue

                        self.repo.save_document(doc)
                        documents_crawled += 1
                        await self.worker.process_document(doc, current_task, objective)

                        # Dynamic child link discovery: if depth permits, discover and enqueue child links
                        if getattr(objective, "max_depth", 1) > 1:
                            parent_req = CrawlRequest(
                                url=doc.url,
                                objective_id=objective.objective_id,
                                research_task_id=current_task.task_id,
                                depth=1,
                            )
                            await self.crawl_engine.discover_and_enqueue_child_links(
                                document=doc,
                                parent_request=parent_req,
                                max_depth=getattr(objective, "max_depth", 2),
                                max_links=2,
                            )

                        # Real-time contact resolution on newly crawled document
                        if self.contact_resolver is not None:
                            try:
                                await self.contact_resolver.resolve_document_contacts(
                                    doc=doc,
                                    objective_id=objective.objective_id,
                                    repo=self.repo,
                                )
                            except Exception as exc:
                                logger.debug("Real-time document contact resolution error: %s", exc)

                # Run Expert Verifier on pending claims
                adjudications = await self.verifier.adjudicate_pending_claims(
                    objective_id=objective.objective_id
                )

                # Real-time contact resolution for newly verified personnel & facility domains
                if self.contact_resolver is not None:
                    try:
                        await self.contact_resolver.resolve_entity_contacts_realtime(
                            objective_id=objective.objective_id,
                            repo=self.repo,
                        )
                    except Exception as exc:
                        logger.debug("Real-time entity contact resolution error: %s", exc)

                # Real-time autonomous matrix materialization
                try:
                    self.repo.materialize_plant_leadership_matrix(objective.objective_id)
                except Exception as exc:
                    logger.debug("Matrix materialization error: %s", exc)

                # If verifier produced disambiguation subtasks, schedule them
                disambig_tasks = [
                    t for adj in adjudications for t in adj.suggested_tasks
                ]
                if disambig_tasks:
                    await self.brain.plan_followup_tasks(
                        objective=objective,
                        missing_fields=[],
                        disambiguation_tasks=disambig_tasks,
                        parent_task=current_task,
                    )

                # Complete task successfully
                TaskStateMachine.transition(current_task, TaskStatus.COMPLETED)
                self.repo.save_task(current_task)
                self.repo.record_event(
                    ResearchEvent(
                        objective_id=objective.objective_id,
                        task_id=current_task.task_id,
                        event_type=EventType.TASK_COMPLETED,
                        payload={"urls_examined": len(discovered_urls)},
                    )
                )

                # Evaluate yield for diminishing returns
                supported_after = len(
                    self.repo.list_claims(
                        objective_id=objective.objective_id,
                        status=[ClaimStatus.SUPPORTED, ClaimStatus.CORROBORATED],
                    )
                )
                if supported_after > supported_before:
                    consecutive_zero_yield_tasks = 0
                else:
                    consecutive_zero_yield_tasks += 1

            except Exception as exc:  # noqa: BLE001 - resilience boundary to prevent orchestrator crash
                consecutive_zero_yield_tasks += 1
                TaskStateMachine.transition(
                    current_task,
                    TaskStatus.FAILED,
                    error_message=str(exc),
                )
                self.repo.record_event(
                    ResearchEvent(
                        objective_id=objective.objective_id,
                        task_id=current_task.task_id,
                        event_type=EventType.TASK_FAILED,
                        payload={
                            "error": str(exc),
                            "retry_count": current_task.retry_count,
                            "max_retries": current_task.max_retries,
                        },
                    )
                )

                # Bug 4.3: If retries remain, transition back to READY to be retried
                if current_task.retry_count < current_task.max_retries:
                    TaskStateMachine.transition(current_task, TaskStatus.READY)
                    self.repo.record_event(
                        ResearchEvent(
                            objective_id=objective.objective_id,
                            task_id=current_task.task_id,
                            event_type=EventType.TASK_CREATED,
                            payload={
                                "requeued_retry": current_task.retry_count,
                                "max_retries": current_task.max_retries,
                            },
                        )
                    )

                self.repo.save_task(current_task)

            tasks_executed += 1

        # Resolve corporate contacts and facility lines (Stage 4)
        if self.contact_resolver is not None:
            try:
                await self.contact_resolver.resolve_contacts_for_objective(
                    objective_id=objective.objective_id,
                    repo=self.repo,
                )
            except Exception as exc:  # noqa: BLE001
                self.repo.record_event(
                    ResearchEvent(
                        objective_id=objective.objective_id,
                        event_type=EventType.RESEARCH_STOPPED,
                        payload={"contact_resolution_error": str(exc)},
                    )
                )

        # Ensure final materialization of clean matrix
        try:
            self.repo.materialize_plant_leadership_matrix(objective.objective_id)
        except Exception as exc:
            logger.debug("Final matrix materialization notice: %s", exc)

        # Advance orderly through remaining stages to Synthesis
        current_stage = self._advance_to_synthesis_stage(
            objective_id=objective.objective_id,
            current_stage=current_stage,
        )

        # 4. Lifecycle termination
        self.repo.record_event(
            ResearchEvent(
                objective_id=objective.objective_id,
                event_type=EventType.RESEARCH_STOPPED,
                payload={
                    "tasks_executed": tasks_executed,
                    "documents_crawled": documents_crawled,
                    "stop_reason": stop_reason or stopping_eval.reason,
                },
            )
        )

        # 5. Synthesize final dossier
        dossier = await self.brain.synthesize_dossier(
            objective=objective,
            total_tasks=tasks_executed,
            total_documents=documents_crawled,
        )

        # Complete Stage 5 (Synthesis)
        self.repo.record_event(
            ResearchEvent(
                objective_id=objective.objective_id,
                event_type=EventType.STAGE_COMPLETED,
                payload={"stage": ResearchStage.SYNTHESIS.value},
            )
        )

        # 6. Autonomous Teardown: regenerate DB viewer HTML and export CSV matrices
        try:
            from scripts.view_db import cmd_export, cmd_html
            db_path = getattr(self.repo.db, "db_path", "data/argus_us_automotive_deep.db")
            if os.path.exists(db_path):
                cmd_html(db_path, "data/db_viewer.html")
                cmd_export(db_path, "data/exports")
                logger.info("Autonomous teardown: updated data/db_viewer.html and data/exports/")
        except Exception as exc:  # noqa: BLE001
            logger.debug("Autonomous teardown export notice: %s", exc)

        return dossier

    def _transition_stage_if_needed(
        self,
        objective: ResearchObjective,
        current_stage: ResearchStage,
        tasks_executed: int,
    ) -> ResearchStage:
        """Progressively advance lifecycle stages based on evidence maturity."""
        entities = self.repo.list_entities(objective_id=objective.objective_id)
        claims = self.repo.list_claims(
            objective_id=objective.objective_id,
            status=[ClaimStatus.SUPPORTED, ClaimStatus.CORROBORATED],
        )

        next_stage = current_stage

        if current_stage == ResearchStage.RECONNAISSANCE:
            # Advance to Operational Mapping once core entities are discovered or first task ran
            if len(entities) > 0 or tasks_executed >= 1:
                next_stage = ResearchStage.OPERATIONAL_MAPPING

        elif current_stage == ResearchStage.OPERATIONAL_MAPPING:
            # Advance to Personnel & Leadership if operational sites/facilities found or tasks progressed
            has_facility_evidence = any(
                "facility" in c.predicate.lower()
                or "plant" in c.predicate.lower()
                or "site" in c.predicate.lower()
                for c in claims
            ) or len(entities) > 1 or tasks_executed >= 2
            if has_facility_evidence:
                next_stage = ResearchStage.PERSONNEL_LEADERSHIP

        elif current_stage == ResearchStage.PERSONNEL_LEADERSHIP:
            # Advance to Contact Resolution once leadership is found or tasks progressed
            has_personnel_evidence = any(
                "head" in c.predicate.lower()
                or "manager" in c.predicate.lower()
                or "director" in c.predicate.lower()
                or "lead" in c.predicate.lower()
                for c in claims
            ) or tasks_executed >= 3
            if has_personnel_evidence:
                next_stage = ResearchStage.CONTACT_RESOLUTION

        if next_stage != current_stage:
            self.repo.record_event(
                ResearchEvent(
                    objective_id=objective.objective_id,
                    event_type=EventType.STAGE_COMPLETED,
                    payload={"stage": current_stage.value},
                )
            )
            self.repo.record_event(
                ResearchEvent(
                    objective_id=objective.objective_id,
                    event_type=EventType.STAGE_STARTED,
                    payload={"stage": next_stage.value},
                )
            )
            return next_stage

        return current_stage

    def _advance_to_synthesis_stage(
        self,
        objective_id: str,
        current_stage: ResearchStage,
    ) -> ResearchStage:
        """Orderly advance through remaining stages to ensure Stage 5 (Synthesis) is reached."""
        stage_order = [
            ResearchStage.RECONNAISSANCE,
            ResearchStage.OPERATIONAL_MAPPING,
            ResearchStage.PERSONNEL_LEADERSHIP,
            ResearchStage.CONTACT_RESOLUTION,
            ResearchStage.SYNTHESIS,
        ]
        curr_idx = stage_order.index(current_stage)

        # Complete each intermediate stage in order up to SYNTHESIS
        for i in range(curr_idx, len(stage_order) - 1):
            stage = stage_order[i]
            next_stage = stage_order[i + 1]
            self.repo.record_event(
                ResearchEvent(
                    objective_id=objective_id,
                    event_type=EventType.STAGE_COMPLETED,
                    payload={"stage": stage.value},
                )
            )
            self.repo.record_event(
                ResearchEvent(
                    objective_id=objective_id,
                    event_type=EventType.STAGE_STARTED,
                    payload={"stage": next_stage.value},
                )
            )

        return ResearchStage.SYNTHESIS
