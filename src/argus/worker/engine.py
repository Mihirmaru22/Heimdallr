import re
from datetime import UTC, datetime

from argus.domain.canonicalizer import (
    GENERIC_ALIASES,
    are_entities_equivalent,
    is_specific_alias,
)
from argus.crawler.models import Document
from argus.domain.claim import Claim, ClaimStatus
from argus.domain.entity import Entity
from argus.domain.event import EventType, ResearchEvent
from argus.domain.evidence import Evidence
from argus.domain.objective import ResearchObjective
from argus.domain.task import ResearchTask
from argus.llm.provider import LLMProvider
from argus.storage.repository import ArgusRepository
from argus.worker.models import (
    ExtractedClaimItem,
    ExtractionPayload,
    WorkerResult,
)
from argus.worker.prompts import WORKER_SYSTEM_PROMPT, build_extraction_prompt



class WorkerEngine:
    """Worker engine for document relevance triage, entity resolution, and grounded claim extraction."""

    def __init__(self, repo: ArgusRepository, llm: LLMProvider) -> None:
        self.repo = repo
        self.llm = llm

    async def process_document(
        self,
        document: Document,
        task: ResearchTask,
        objective: ResearchObjective,
    ) -> WorkerResult:
        """Evaluate document relevance and extract grounded entities and claims."""
        prompt = build_extraction_prompt(
            objective_target=objective.target,
            intelligence_goal=objective.intelligence_goal,
            task_title=task.title,
            task_description=task.description,
            doc_title=document.title or "",
            doc_url=document.url,
            doc_text=document.text_content,
            required_fields=objective.required_fields,
            content_units=document.content_units,
        )

        payload: ExtractionPayload = await self.llm.generate_structured(
            prompt=prompt,
            response_model=ExtractionPayload,
            system_prompt=WORKER_SYSTEM_PROMPT,
        )

        # 1. Relevance Triage Guardrail
        if not payload.relevance.is_relevant:
            self.repo.record_event(
                ResearchEvent(
                    objective_id=objective.objective_id,
                    task_id=task.task_id,
                    event_type=EventType.EVIDENCE_ATTACHED,
                    payload={
                        "status": "irrelevant",
                        "url": document.url,
                        "reasoning": payload.relevance.reasoning,
                        "confidence": payload.relevance.confidence,
                    },
                )
            )
            return WorkerResult(
                document_url=document.url,
                is_relevant=False,
                suggested_followup_tasks=payload.suggested_followup_tasks,
            )

        # 2. Entity Resolution & Persistence
        entities_created: list[Entity] = []
        entities_updated: list[Entity] = []

        # Load existing entities from repo to resolve against
        known_entities = self.repo.list_entities(objective_id=objective.objective_id)
        resolved_entities: dict[str, Entity] = {}

        # Index known entities by canonical name, specific aliases, and fuzzy tokens
        def find_existing_entity(
            name: str, aliases: list[str], entity_type: str
        ) -> Entity | None:
            for candidate in known_entities:
                if are_entities_equivalent(
                    name1=name,
                    type1=entity_type,
                    name2=candidate.canonical_name,
                    type2=candidate.entity_type,
                    aliases1=aliases,
                    aliases2=candidate.aliases,
                ):
                    return candidate
            return None

        for item in payload.entities:
            matched = find_existing_entity(item.name, item.aliases, item.entity_type)
            if matched is not None:
                # Upgrade generic entity_type if new type is more specific
                if matched.entity_type == "entity" and item.entity_type != "entity":
                    matched.entity_type = item.entity_type

                # Update aliases and attributes (filtering out generic stopwords)
                updated_aliases = [
                    a
                    for a in set(matched.aliases) | set(item.aliases) | {item.name}
                    if is_specific_alias(a)
                    and a.strip().lower() != matched.canonical_name.strip().lower()
                ]

                updated_attributes = {**matched.attributes, **item.attributes}
                matched.aliases = updated_aliases
                matched.attributes = updated_attributes
                matched.updated_at = datetime.now(UTC)

                self.repo.save_entity(matched)
                entities_updated.append(matched)
                resolved_entities[item.name.strip().lower()] = matched
            else:
                filtered_aliases = [a for a in item.aliases if is_specific_alias(a)]
                new_entity = Entity(
                    entity_type=item.entity_type,
                    canonical_name=item.name,
                    aliases=filtered_aliases,
                    attributes=item.attributes,
                    objective_id=objective.objective_id,
                )
                self.repo.save_entity(new_entity)
                known_entities.append(new_entity)
                entities_created.append(new_entity)
                resolved_entities[item.name.strip().lower()] = new_entity

        # 3. Grounded Evidence & Claims Extraction
        evidence_created: list[Evidence] = []
        claims_created: list[Claim] = []

        for claim_item in payload.claims:
            # Epistemic quote validation
            char_start, char_end = self._find_passage_offsets(
                document.text_content, claim_item.verbatim_passage
            )

            unit_id = None
            if char_start is not None:
                matched_unit = document.find_unit_for_offset(char_start)
                if matched_unit:
                    unit_id = matched_unit.unit_id

            evidence = Evidence(
                source_id=document.content_hash,
                url=document.url,
                passage=claim_item.verbatim_passage,
                char_start=char_start,
                char_end=char_end,
                confidence=claim_item.confidence,
                published_at=document.published_at,
                document_id=document.document_id,
                unit_id=unit_id,
                content_hash=document.content_hash,
                canonical_url=document.canonical_url,
            )
            self.repo.save_evidence(evidence)
            evidence_created.append(evidence)

            # Resolve Subject Entity
            subject_entity = self._resolve_or_create_subject(
                claim_item=claim_item,
                resolved_entities=resolved_entities,
                known_entities=known_entities,
                entities_created=entities_created,
                objective_id=objective.objective_id,
            )

            # Resolve Object Entity if applicable
            object_entity_id = self._resolve_object_entity(
                object_value=claim_item.object_value,
                known_entities=known_entities,
            )

            claim = Claim(
                subject_entity_id=subject_entity.entity_id,
                predicate=claim_item.predicate.strip().upper(),
                object_value=claim_item.object_value,
                object_entity_id=object_entity_id,
                status=ClaimStatus.PENDING,
                evidence_ids=[evidence.evidence_id],
                confidence=claim_item.confidence,
                objective_id=objective.objective_id,
            )
            self.repo.save_claim(claim)
            claims_created.append(claim)

        # 4. Record Audit Event
        self.repo.record_event(
            ResearchEvent(
                objective_id=objective.objective_id,
                task_id=task.task_id,
                event_type=EventType.EVIDENCE_ATTACHED,
                payload={
                    "status": "extracted",
                    "url": document.url,
                    "entities_created": len(entities_created),
                    "entities_updated": len(entities_updated),
                    "evidence_created": len(evidence_created),
                    "claims_created": len(claims_created),
                },
            )
        )

        return WorkerResult(
            document_url=document.url,
            is_relevant=True,
            entities_created=entities_created,
            entities_updated=entities_updated,
            evidence_created=evidence_created,
            claims_created=claims_created,
            suggested_followup_tasks=payload.suggested_followup_tasks,
        )

    def _find_passage_offsets(
        self, text: str, passage: str
    ) -> tuple[int | None, int | None]:
        """Find character start and end of verbatim passage in document text.

        Hierarchy:
        1. Exact substring match
        2. Whitespace-resilient regex match (LF/CRLF and collapsed spaces)
        3. Punctuation/quote normalized match (curly quotes, dashes)
        4. If not grounded, return (None, None) - never fabricate coordinates.
        """
        cleaned_passage = passage.strip()
        if not cleaned_passage or not text:
            return None, None

        # 1. Fast exact substring match
        idx = text.find(cleaned_passage)
        if idx != -1:
            return idx, idx + len(cleaned_passage)

        # 2. Whitespace-resilient regex match (handles \r\n vs \n and collapsed spaces)
        words = [w for w in re.split(r"\s+", cleaned_passage) if w]
        if words:
            pattern = r"\s+".join(re.escape(w) for w in words)
            try:
                match = re.search(pattern, text)
                if match:
                    return match.start(), match.end()
            except re.error:
                pass

        # 3. Punctuation and quote normalized matching
        def normalize_chars(s: str) -> str:
            return (
                s.replace("“", '"')
                .replace("”", '"')
                .replace("‘", "'")
                .replace("’", "'")
                .replace("—", "-")
                .replace("–", "-")
                .replace("\u00a0", " ")
            )

        norm_text = normalize_chars(text)
        norm_passage = normalize_chars(cleaned_passage)
        if len(norm_text) == len(text):
            idx_norm = norm_text.find(norm_passage)
            if idx_norm != -1:
                return idx_norm, idx_norm + len(norm_passage)

            words_norm = [w for w in re.split(r"\s+", norm_passage) if w]
            if words_norm:
                pattern_norm = r"\s+".join(re.escape(w) for w in words_norm)
                try:
                    match_norm = re.search(pattern_norm, norm_text)
                    if match_norm:
                        return match_norm.start(), match_norm.end()
                except re.error:
                    pass

        return None, None

    def _resolve_or_create_subject(
        self,
        claim_item: ExtractedClaimItem,
        resolved_entities: dict[str, Entity],
        known_entities: list[Entity],
        entities_created: list[Entity],
        objective_id: str | None = None,
    ) -> Entity:
        """Retrieve resolved subject entity or create fallback entity."""
        norm_subj = claim_item.subject_name.strip().lower()
        if norm_subj in resolved_entities:
            return resolved_entities[norm_subj]

        # Check in known_entities using are_entities_equivalent
        for ent in known_entities:
            if are_entities_equivalent(
                name1=claim_item.subject_name,
                type1="entity",
                name2=ent.canonical_name,
                type2=ent.entity_type,
                aliases1=[],
                aliases2=ent.aliases,
            ):
                resolved_entities[norm_subj] = ent
                return ent

        # Fallback creation
        new_ent = Entity(
            entity_type="entity",
            canonical_name=claim_item.subject_name,
            objective_id=objective_id,
        )
        self.repo.save_entity(new_ent)
        known_entities.append(new_ent)
        entities_created.append(new_ent)
        resolved_entities[norm_subj] = new_ent
        return new_ent

    def _resolve_object_entity(
        self,
        object_value: str,
        known_entities: list[Entity],
    ) -> str | None:
        """Check if object value matches a known entity canonical name or alias."""
        for ent in known_entities:
            if are_entities_equivalent(
                name1=object_value,
                type1="entity",
                name2=ent.canonical_name,
                type2=ent.entity_type,
                aliases1=[],
                aliases2=ent.aliases,
            ):
                return ent.entity_id
        return None
