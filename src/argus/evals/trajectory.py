"""Non-intrusive trajectory recorder and auditor for the Argus Evaluation Harness.

Couples to Argus exclusively via immutable versioned audit events and repository
state, observing the full research lifecycle without modifying production code.
"""

from datetime import UTC, datetime
from typing import Any

from argus.domain.event import EventType, ResearchEvent
from argus.evals.models import TaskTrajectory, TrajectoryEvent
from argus.storage.repository import ArgusRepository


class TrajectoryRecorder:
    """Reconstructs and audits execution trajectories from immutable audit events."""

    @classmethod
    def from_repository(
        cls,
        task_id: str,
        objective_id: str,
        repo: ArgusRepository,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        stop_reason: str = "",
    ) -> TaskTrajectory:
        """Extract trajectory directly from repository events without runtime intrusion."""
        events: list[ResearchEvent] = repo.list_events(objective_id=objective_id)
        return cls.from_events(
            task_id=task_id,
            objective_id=objective_id,
            events=events,
            repo=repo,
            start_time=start_time,
            end_time=end_time,
            stop_reason=stop_reason,
        )

    @classmethod
    def from_events(
        cls,
        task_id: str,
        objective_id: str,
        events: list[ResearchEvent],
        repo: ArgusRepository | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        stop_reason: str = "",
    ) -> TaskTrajectory:
        """Construct trajectory schema from an event stream."""
        traj_events: list[TrajectoryEvent] = []
        queries: list[str] = []
        urls_crawled: list[str] = []
        security_violations: list[str] = []
        llm_calls_count = 0
        tokens_estimated = 0
        contradictions_detected = 0

        effective_start = start_time or (events[0].timestamp if events else datetime.now(UTC))
        effective_end = end_time or (events[-1].timestamp if events else datetime.now(UTC))

        disallowed_hosts = {"169.254.169.254", "localhost", "127.0.0.1", "metadata.google.internal"}

        for ev in events:
            payload = ev.payload or {}
            ev_type_str = ev.event_type.value if hasattr(ev.event_type, "value") else str(ev.event_type)

            # Map to trajectory event
            traj_events.append(
                TrajectoryEvent(
                    event_id=ev.event_id,
                    timestamp=ev.timestamp,
                    event_type=ev_type_str,
                    stage=payload.get("stage"),
                    task_id=ev.task_id,
                    details=payload,
                )
            )

            # Audit queries
            if ev.event_type in (EventType.SEARCH_EXECUTED, "search_executed"):
                q = payload.get("query", "")
                if q and q not in queries:
                    queries.append(q)
                # Estimate search LLM/tokens
                tokens_estimated += len(q.split()) * 2

            # Audit acquired docs & URLs
            if ev.event_type in (EventType.CRAWL_COMPLETED, EventType.CRAWL_REQUEST_SUCCEEDED, "document_crawled", "document_created"):
                u = payload.get("url", "")
                if u and u not in urls_crawled:
                    urls_crawled.append(u)
                    # Check for SSRF in trajectory
                    for dis in disallowed_hosts:
                        if dis in u.lower():
                            security_violations.append(f"SSRF_ATTEMPT: Disallowed target {u}")

            # Audit extractions
            if ev.event_type in (EventType.EVIDENCE_ATTACHED, EventType.ENTITY_EXTRACTED, EventType.CLAIM_CREATED, "extraction_completed"):
                llm_calls_count += 1
                tokens_estimated += 1500  # Conservative estimate per extraction

            # Audit verifications
            if ev.event_type in (EventType.VERIFICATION_COMPLETED, "verification_completed"):
                llm_calls_count += 1
                tokens_estimated += 800

            if ev.event_type in (EventType.CONTRADICTION_DETECTED, "contradiction_detected"):
                contradictions_detected += 1

        duration_sec = max(0.01, (effective_end - effective_start).total_seconds())

        # Pull actual entities/claims count from repo if available
        docs_count = len(urls_crawled)
        claims_extracted = 0
        claims_verified = 0

        if repo is not None:
            all_claims = repo.list_claims(objective_id=objective_id)
            claims_extracted = len(all_claims)
            claims_verified = sum(1 for c in all_claims if c.is_verified())
            if not urls_crawled:
                urls_crawled = list(repo.get_crawled_urls())
                docs_count = len(urls_crawled)

        # Check stopping behavior
        premature = False
        wasteful = False

        if "diminishing_returns" in stop_reason and claims_extracted == 0:
            premature = True

        if claims_extracted >= 10 and len(queries) > 25:
            wasteful = True

        # Cost estimate: ~$0.001 per 1k tokens
        cost_usd = (tokens_estimated / 1000.0) * 0.0015

        return TaskTrajectory(
            task_id=task_id,
            objective_id=objective_id,
            start_time=effective_start,
            end_time=effective_end,
            duration_seconds=duration_sec,
            events=traj_events,
            queries_issued=queries,
            urls_crawled=urls_crawled,
            documents_acquired_count=docs_count,
            claims_extracted_count=claims_extracted,
            claims_verified_count=claims_verified,
            llm_calls_count=max(llm_calls_count, 1),
            tokens_estimated=max(tokens_estimated, 500),
            stop_reason=stop_reason,
            premature_stop=premature,
            wasteful_continuation=wasteful,
            security_violations=security_violations,
            cost_estimate_usd=cost_usd,
        )
