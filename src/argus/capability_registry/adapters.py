"""Heimdallr V3.1: Capability Adapters.

Wraps existing production specialists and generalist research engines behind a
uniform capability execution interface without modifying their underlying implementations:
- ArgusResearchAdapter
- IdentitySpecialistAdapter
- InfrastructureSpecialistAdapter
- CorporateSpecialistAdapter
- ChallengerIdentityAdapter (Clean-room second implementation)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import concurrent.futures
import threading
import time
from typing import Any, Dict, List, Optional
import uuid

from argus.specialists.corporate import CorporateProbeSpecialist
from argus.specialists.identity import IdentityProbeSpecialist
from argus.specialists.infrastructure import InfrastructureProbeSpecialist
from argus.specialists.outcome import SpecialistOutcome, SpecialistStatus


def execute_with_timeout(func: Any, timeout_sec: float, *args: Any, **kwargs: Any) -> Any:
    """Execute a specialist callable with hard timeout enforcement using ThreadPoolExecutor."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args, **kwargs)
        return future.result(timeout=timeout_sec)


class BaseCapabilityAdapter(ABC):
    """Abstract capability execution adapter.

    Every adapter (vertical) can use the shared free language models (``self.llm``, for reading
    and writing text) and the shared Laya decision maker (``self.decisions``, for every judgment).
    """

    @property
    def llm(self) -> Any:
        """The shared free-model service (free OpenRouter models, then local), or None if none is set up."""
        from argus.llm.free_models import get_free_model_service

        return get_free_model_service()

    @property
    def decisions(self) -> Any:
        from argus.brain.decisions import get_decisions

        return get_decisions()

    @abstractmethod
    def execute(self, inputs: Dict[str, Any], corpus: Any = None) -> Dict[str, Any]:
        """Execute capability operation and return structured observations."""
        raise NotImplementedError

def simulated_registry(kind: str) -> Dict[str, Dict[str, Any]]:
    """Frozen benchmark registry for a specialist. Only for benchmark and test runs.

    These records are invented fixtures (e.g. "AutoTech Corporation"); live
    investigations must never read them.
    """
    if kind == "identity":
        from argus.evals.vertical_corpus import VERTICAL_PLATFORM_REGISTRY
        return VERTICAL_PLATFORM_REGISTRY
    if kind == "infrastructure":
        from argus.evals.infrastructure_corpus import INFRASTRUCTURE_REGISTRY
        return INFRASTRUCTURE_REGISTRY
    if kind == "corporate":
        from argus.evals.corporate_corpus import CORPORATE_REGISTRY_DATABASE
        return CORPORATE_REGISTRY_DATABASE
    raise KeyError(f"No simulated registry for '{kind}'")


class NoLiveSourceAdapter(BaseCapabilityAdapter):
    """Stands in for a specialist whose only data is a frozen benchmark corpus.

    Outside benchmark runs it reports that no live source exists instead of
    returning invented records; the failure surfaces in the report's limitations.
    """

    def __init__(self, implementation_id: str, capability: str) -> None:
        self.implementation_id = implementation_id
        self.capability = capability

    def execute(self, inputs: Dict[str, Any], corpus: Any = None) -> Dict[str, Any]:
        return {
            "execution_id": f"exec_{uuid.uuid4().hex[:8]}",
            "implementation_id": self.implementation_id,
            "query": inputs.get("query", ""),
            "status": "FAILED",
            "error": (
                f"No live data source is configured for {self.capability}; "
                "frozen benchmark records are not used outside benchmark runs."
            ),
            "documents_count": 0,
            "documents": [],
            "combined_text": "",
            "authoritative": False,
        }


class ArgusResearchAdapter(BaseCapabilityAdapter):
    """Wraps Argus generalist search and corpus retrieval."""

    def execute(self, inputs: Dict[str, Any], corpus: Any = None) -> Dict[str, Any]:
        query = inputs.get("query", "")
        limit = inputs.get("limit", 3)
        start_t = time.perf_counter()

        retrieved_docs: List[Any] = []
        if corpus and hasattr(corpus, "search"):
            retrieved_docs = corpus.search(query, limit=limit)

        text_content = " ".join(getattr(d, "text_content", str(d)) for d in retrieved_docs)
        elapsed = time.perf_counter() - start_t

        return {
            "execution_id": f"exec_{uuid.uuid4().hex[:8]}",
            "capability_id": "general_web_research",
            "implementation_id": "impl_argus_generalist_v1",
            "query": query,
            "documents_count": len(retrieved_docs),
            "documents": [
                {
                    "doc_id": getattr(d, "doc_id", f"doc_{i}"),
                    "title": getattr(d, "title", "Web Document"),
                    "url": getattr(d, "url", ""),
                    "text": getattr(d, "text_content", str(d)),
                    "source_type": getattr(d, "source_type", "web"),
                }
                for i, d in enumerate(retrieved_docs)
            ],
            "combined_text": text_content,
            "runtime_sec": elapsed,
            "epistemic_nature": "OBSERVATION",
            "authoritative": False,
        }


class IdentitySpecialistAdapter(BaseCapabilityAdapter):
    """Wraps IdentityProbeSpecialist for developer persona and identity resolution."""

    def __init__(self, specialist: Optional[IdentityProbeSpecialist] = None, simulated: bool = False) -> None:
        if specialist is None:
            registry = simulated_registry("identity") if simulated else None
            self.specialist = IdentityProbeSpecialist(platform_registry=registry)
        else:
            self.specialist = specialist

    def execute(self, inputs: Dict[str, Any], corpus: Any = None) -> Dict[str, Any]:
        identifier = inputs.get("username") or inputs.get("identifier") or inputs.get("entity_name") or inputs.get("query", "")
        if " " in identifier and inputs.get("entity_name") and " " not in inputs.get("entity_name"):
            identifier = inputs.get("entity_name")
        starting_platform = inputs.get("starting_platform")
        target_entity_context = inputs.get("target_entity_context") or inputs.get("known_context") or {}
        timeout_sec = float(inputs.get("timeout_sec", 5.0))
        start_t = time.perf_counter()

        from argus.specialists.identity.contract import (
            IdentityProbeRequest,
            IdentifierType,
            InvestigationConstraints,
        )

        req = IdentityProbeRequest(
            identifier=identifier,
            identifier_type=IdentifierType.USERNAME,
            starting_platform=starting_platform,
            target_entity_context=target_entity_context,
            constraints=InvestigationConstraints(
                timeout_per_probe_sec=timeout_sec,
                permit_delimiter_permutations=True,
                strict_provenance=True,
                starting_platform=starting_platform,
            ),
        )

        discovered_entities: List[str] = []
        candidate_claims: List[Dict[str, Any]] = []
        docs: List[Dict[str, Any]] = []
        status = "SUCCESS"
        error_msg = None
        probe_res = None

        try:
            probe_res = execute_with_timeout(self.specialist.probe_identifier, timeout_sec, req)
            for c in probe_res.candidates:
                discovered_entities.append(c.candidate_entity)
                docs.append({
                    "doc_id": f"rel_ident_{uuid.uuid4().hex[:8]}",
                    "title": f"Identity Candidate: {c.source_platform} ({c.candidate_entity})",
                    "url": c.source_url,
                    "text": c.supporting_observation,
                    "source_type": "identity_probe",
                    "payload": c.model_dump(),
                    "is_authoritative": False,
                    "confidence": c.confidence,
                    "epistemic_status": c.epistemic_status.value,
                    "is_starting_account": c.is_starting_account,
                    "is_private": c.is_private,
                    "private_content_accessed": c.private_content_accessed,
                    "retrieval_mode": getattr(c, "retrieval_mode", "FIXTURE_SIMULATION"),
                    "is_live": getattr(c, "is_live", False),
                    "response_content_sha256": getattr(c, "response_content_sha256", None),
                    "observation_record_sha256": getattr(c, "observation_record_sha256", None),
                })
                candidate_claims.append({
                    "subject": identifier,
                    "predicate": "candidate_profile",
                    "object": f"Discovered candidate profile on {c.source_platform}: {c.source_url}. {c.supporting_observation}",
                    "status": "SUPPORTED",
                    "source_url": c.source_url,
                    "source_passage": c.supporting_observation[:300],
                    "is_starting_account": c.is_starting_account,
                    "is_private": c.is_private,
                    "retrieval_mode": getattr(c, "retrieval_mode", "FIXTURE_SIMULATION"),
                    "is_live": getattr(c, "is_live", False),
                    "response_content_sha256": getattr(c, "response_content_sha256", None),
                    "observation_record_sha256": getattr(c, "observation_record_sha256", None),
                })

            # Also populate structured claims from probe_res.claims preserving epistemic boundaries
            if getattr(probe_res, "claims", None):
                for ic in probe_res.claims:
                    candidate_claims.append({
                        "subject": ic.subject,
                        "predicate": ic.claim_type.value if hasattr(ic.claim_type, "value") else str(ic.claim_type),
                        "object": ic.statement,
                        "status": ic.status,
                        "is_private": ic.is_private,
                        "authorized_access": ic.authorized_access,
                        "content_retrieved": ic.content_retrieved,
                        "source_url": ic.source_url,
                        "retrieval_mode": getattr(ic, "retrieval_mode", "FIXTURE_SIMULATION"),
                        "is_live": getattr(ic, "is_live", False),
                        "response_content_sha256": getattr(ic, "response_content_sha256", None),
                        "observation_record_sha256": getattr(ic, "observation_record_sha256", None),
                        "provenance": ic.provenance,
                    })
        except (concurrent.futures.TimeoutError, TimeoutError):
            status = "TIMEOUT"
            error_msg = f"Identity specialist timed out after {timeout_sec}s"
        except Exception as e:
            status = "FAILED"
            error_msg = str(e)

        # Merge corpus search results if available
        retrieved_docs: List[Any] = []
        if corpus and hasattr(corpus, "search"):
            retrieved_docs = corpus.search(identifier, limit=3)
            for i, d in enumerate(retrieved_docs):
                docs.append({
                    "doc_id": getattr(d, "doc_id", f"doc_ident_{i}"),
                    "title": getattr(d, "title", "Identity Document"),
                    "url": getattr(d, "url", ""),
                    "text": getattr(d, "text_content", str(d)),
                    "source_type": getattr(d, "source_type", "identity_record"),
                })

        text_content = " ".join(d.get("text", "") for d in docs)
        elapsed = time.perf_counter() - start_t

        # Determine granular outcome
        if status == "TIMEOUT":
            outcome = SpecialistOutcome.TIMEOUT
        elif status == "FAILED":
            outcome = SpecialistOutcome.SOURCE_ERROR
        else:
            raw_outcome = getattr(probe_res, "outcome", None)
            if isinstance(raw_outcome, SpecialistOutcome):
                outcome = raw_outcome
            elif isinstance(raw_outcome, str):
                try:
                    outcome = SpecialistOutcome(raw_outcome)
                except ValueError:
                    outcome = SpecialistOutcome.SUCCESS_WITH_RESULTS if docs else SpecialistOutcome.SUCCESS_EMPTY
            else:
                outcome = SpecialistOutcome.SUCCESS_WITH_RESULTS if docs else SpecialistOutcome.SUCCESS_EMPTY

            if retrieved_docs and outcome in (SpecialistOutcome.SOURCE_UNAVAILABLE, SpecialistOutcome.SOURCE_ERROR):
                outcome = SpecialistOutcome.PARTIAL_SUCCESS

        res_status = SpecialistStatus(outcome.value)
        errors_list: list[str] = list(getattr(probe_res, "errors", [])) if probe_res else []
        if error_msg and error_msg not in errors_list:
            errors_list.append(error_msg)

        res_dict = {
            "execution_id": f"exec_{uuid.uuid4().hex[:8]}",
            "capability_id": "identity_resolution",
            "implementation_id": "impl_identity_probe_specialist_v1",
            "identifier": identifier,
            "starting_platform": starting_platform,
            "starting_account": probe_res.starting_account.model_dump() if (probe_res and probe_res.starting_account) else None,
            "sources_queried": getattr(probe_res, "sources_queried", []),
            "platforms_queried": getattr(probe_res, "platforms_queried", 0),
            "platforms_skipped": getattr(probe_res, "platforms_skipped", 0),
            "platforms_available": getattr(probe_res, "platforms_available", 0),
            "documents_count": len(docs),
            "documents": docs,
            "entities": list(dict.fromkeys(discovered_entities)),
            "claims": candidate_claims,
            "combined_text": text_content,
            "runtime_sec": elapsed,
            "epistemic_nature": "CANDIDATE",
            "authoritative": False,
            "status": res_status,
            "outcome": outcome.value,
            "errors": errors_list,
        }
        if error_msg:
            res_dict["error"] = error_msg
        return res_dict


class InfrastructureSpecialistAdapter(BaseCapabilityAdapter):
    """Wraps InfrastructureProbeSpecialist for DNS, TLS/SAN, and host discovery."""

    def __init__(self, specialist: Optional[InfrastructureProbeSpecialist] = None, simulated: bool = False) -> None:
        if specialist is None:
            registry = simulated_registry("infrastructure") if simulated else None
            self.specialist = InfrastructureProbeSpecialist(registry=registry)
        else:
            self.specialist = specialist

    def execute(self, inputs: Dict[str, Any], corpus: Any = None) -> Dict[str, Any]:
        target = inputs.get("target_domain") or inputs.get("domain") or inputs.get("query", "")
        timeout_sec = float(inputs.get("timeout_sec", 5.0))
        start_t = time.perf_counter()

        from argus.specialists.infrastructure.contract import (
            InfrastructureProbeRequest,
            InfrastructureInvestigationConstraints,
        )

        req = InfrastructureProbeRequest(
            domain=target,
            constraints=InfrastructureInvestigationConstraints(
                timeout_sec=timeout_sec,
                strict_provenance=True,
            ),
        )

        discovered_entities: List[str] = []
        candidate_claims: List[Dict[str, Any]] = []
        docs: List[Dict[str, Any]] = []
        status = "SUCCESS"
        error_msg = None
        probe_res = None

        try:
            probe_res = execute_with_timeout(self.specialist.enumerate_infrastructure, timeout_sec, req)
            for asset in probe_res.assets:
                discovered_entities.append(asset.hostname)
                obs_text = getattr(asset, "supporting_observation", getattr(asset, "observation", f"Asset {asset.hostname}"))
                docs.append({
                    "doc_id": asset.asset_id,
                    "title": f"Infrastructure Asset: {asset.hostname}",
                    "url": f"https://{asset.hostname}",
                    "text": obs_text,
                    "source_type": asset.asset_type.value,
                    "payload": asset.model_dump(),
                    "is_authoritative": False,
                    "confidence": asset.confidence,
                    "epistemic_status": asset.epistemic_status.value,
                })
                candidate_claims.append({
                    "subject": asset.parent_domain,
                    "predicate": asset.relationship_type.value,
                    "object": obs_text,
                    "status": "SUPPORTED",
                    "source_url": f"https://{asset.hostname}",
                    "source_passage": obs_text[:300],
                })
        except (concurrent.futures.TimeoutError, TimeoutError):
            status = "TIMEOUT"
            error_msg = f"Infrastructure specialist timed out after {timeout_sec}s"
        except Exception as e:
            status = "FAILED"
            error_msg = str(e)

        # Merge corpus search results if available
        retrieved_docs: List[Any] = []
        if corpus and hasattr(corpus, "search"):
            retrieved_docs = corpus.search(target, limit=3)
            for i, d in enumerate(retrieved_docs):
                docs.append({
                    "doc_id": getattr(d, "doc_id", f"doc_infra_{i}"),
                    "title": getattr(d, "title", "Infrastructure Record"),
                    "url": getattr(d, "url", ""),
                    "text": getattr(d, "text_content", str(d)),
                    "source_type": getattr(d, "source_type", "infrastructure_record"),
                })

        text_content = " ".join(d.get("text", "") for d in docs)
        elapsed = time.perf_counter() - start_t

        # Determine granular outcome
        if status == "TIMEOUT":
            outcome = SpecialistOutcome.TIMEOUT
        elif status == "FAILED":
            outcome = SpecialistOutcome.SOURCE_ERROR
        else:
            raw_outcome = getattr(probe_res, "outcome", None)
            if isinstance(raw_outcome, SpecialistOutcome):
                outcome = raw_outcome
            elif isinstance(raw_outcome, str):
                try:
                    outcome = SpecialistOutcome(raw_outcome)
                except ValueError:
                    outcome = SpecialistOutcome.SUCCESS_WITH_RESULTS if docs else SpecialistOutcome.SUCCESS_EMPTY
            else:
                outcome = SpecialistOutcome.SUCCESS_WITH_RESULTS if docs else SpecialistOutcome.SUCCESS_EMPTY

            if retrieved_docs and outcome in (SpecialistOutcome.SOURCE_UNAVAILABLE, SpecialistOutcome.SOURCE_ERROR):
                outcome = SpecialistOutcome.PARTIAL_SUCCESS

        res_status = SpecialistStatus(outcome.value)
        errors_list: list[str] = list(getattr(probe_res, "errors", [])) if probe_res else []
        if error_msg and error_msg not in errors_list:
            errors_list.append(error_msg)

        res_dict = {
            "execution_id": f"exec_{uuid.uuid4().hex[:8]}",
            "capability_id": "infrastructure_discovery",
            "implementation_id": "impl_infrastructure_probe_specialist_v1",
            "target": target,
            "documents_count": len(docs),
            "documents": docs,
            "entities": list(dict.fromkeys(discovered_entities)),
            "claims": candidate_claims,
            "combined_text": text_content,
            "runtime_sec": elapsed,
            "epistemic_nature": "CANDIDATE",
            "authoritative": False,
            "status": res_status,
            "outcome": outcome.value,
            "errors": errors_list,
        }
        if error_msg:
            res_dict["error"] = error_msg
        return res_dict


class CorporateSpecialistAdapter(BaseCapabilityAdapter):
    """Wraps CorporateProbeSpecialist for statutory registries and restatement resolution."""

    def __init__(self, specialist: Optional[CorporateProbeSpecialist] = None, simulated: bool = False) -> None:
        if specialist is None:
            registry = simulated_registry("corporate") if simulated else None
            self.specialist = CorporateProbeSpecialist(registry_database=registry)
        else:
            self.specialist = specialist

    def execute(self, inputs: Dict[str, Any], corpus: Any = None) -> Dict[str, Any]:
        company = inputs.get("company_name") or inputs.get("entity_name") or inputs.get("query", "")
        corp_id = inputs.get("corporate_identifier")
        as_of_date = inputs.get("as_of_date")
        timeout_sec = float(inputs.get("timeout_sec", 5.0))
        start_t = time.perf_counter()

        from argus.specialists.corporate.contract import (
            CorporateProbeRequest,
            CorporateInvestigationConstraints,
        )

        req = CorporateProbeRequest(
            entity_name=company,
            corporate_identifier=corp_id,
            as_of_date=as_of_date,
            constraints=CorporateInvestigationConstraints(
                as_of_date=as_of_date,
                strict_provenance=True,
            ),
        )

        discovered_entities: List[str] = []
        candidate_claims: List[Dict[str, Any]] = []
        docs: List[Dict[str, Any]] = []
        status = "SUCCESS"
        error_msg = None
        probe_res = None

        try:
            probe_res = execute_with_timeout(self.specialist.probe_corporate_entity, timeout_sec, req)
            for rel in probe_res.relationships:
                discovered_entities.extend([rel.subject_entity, rel.object_entity])
                docs.append({
                    "doc_id": rel.relationship_id,
                    "title": f"Corporate Registry Filing: {rel.subject_entity} - {rel.object_entity}",
                    "url": rel.source_url,
                    "text": rel.observation,
                    "source_type": rel.source_registry.lower(),
                    "payload": rel.model_dump(),
                    "is_authoritative": False,
                    "confidence": rel.confidence,
                    "epistemic_status": rel.epistemic_status.value,
                })
                candidate_claims.append({
                    "subject": rel.subject_entity,
                    "predicate": rel.predicate.value,
                    "object": rel.observation,
                    "status": "SUPPORTED",
                    "source_url": rel.source_url,
                    "source_passage": rel.observation[:300],
                })
        except (concurrent.futures.TimeoutError, TimeoutError):
            status = "TIMEOUT"
            error_msg = f"Corporate specialist timed out after {timeout_sec}s"
        except Exception as e:
            status = "FAILED"
            error_msg = str(e)

        # Merge corpus search results if available
        retrieved_docs: List[Any] = []
        if corpus and hasattr(corpus, "search"):
            retrieved_docs = corpus.search(company, limit=3)
            for i, d in enumerate(retrieved_docs):
                docs.append({
                    "doc_id": getattr(d, "doc_id", f"doc_corp_{i}"),
                    "title": getattr(d, "title", "Corporate Registry Filing"),
                    "url": getattr(d, "url", ""),
                    "text": getattr(d, "text_content", str(d)),
                    "source_type": getattr(d, "source_type", "corporate_registry"),
                })

        text_content = " ".join(d.get("text", "") for d in docs)
        elapsed = time.perf_counter() - start_t

        # Determine granular outcome
        if status == "TIMEOUT":
            outcome = SpecialistOutcome.TIMEOUT
        elif status == "FAILED":
            outcome = SpecialistOutcome.SOURCE_ERROR
        else:
            raw_outcome = getattr(probe_res, "outcome", None)
            if isinstance(raw_outcome, SpecialistOutcome):
                outcome = raw_outcome
            elif isinstance(raw_outcome, str):
                try:
                    outcome = SpecialistOutcome(raw_outcome)
                except ValueError:
                    outcome = SpecialistOutcome.SUCCESS_WITH_RESULTS if docs else SpecialistOutcome.SUCCESS_EMPTY
            else:
                outcome = SpecialistOutcome.SUCCESS_WITH_RESULTS if docs else SpecialistOutcome.SUCCESS_EMPTY

            if retrieved_docs and outcome in (SpecialistOutcome.SOURCE_UNAVAILABLE, SpecialistOutcome.SOURCE_ERROR):
                outcome = SpecialistOutcome.PARTIAL_SUCCESS

        res_status = SpecialistStatus(outcome.value)
        errors_list: list[str] = list(getattr(probe_res, "errors", [])) if probe_res else []
        if error_msg and error_msg not in errors_list:
            errors_list.append(error_msg)

        res_dict = {
            "execution_id": f"exec_{uuid.uuid4().hex[:8]}",
            "capability_id": "corporate_registry_intelligence",
            "implementation_id": "impl_corporate_registry_specialist_v1",
            "company": company,
            "documents_count": len(docs),
            "documents": docs,
            "entities": list(dict.fromkeys(discovered_entities)),
            "claims": candidate_claims,
            "combined_text": text_content,
            "runtime_sec": elapsed,
            "epistemic_nature": "CANDIDATE",
            "authoritative": False,
            "status": res_status,
            "outcome": outcome.value,
            "errors": errors_list,
        }
        if error_msg:
            res_dict["error"] = error_msg
        return res_dict


class ChallengerIdentityAdapter(BaseCapabilityAdapter):
    """Independent clean-room challenger adapter for identity_resolution."""

    def execute(self, inputs: Dict[str, Any], corpus: Any = None) -> Dict[str, Any]:
        identifier = inputs.get("identifier") or inputs.get("query", "")
        start_t = time.perf_counter()

        retrieved_docs: List[Any] = []
        if corpus and hasattr(corpus, "search"):
            retrieved_docs = corpus.search(identifier, limit=3)

        text_content = " ".join(getattr(d, "text_content", str(d)) for d in retrieved_docs)
        elapsed = time.perf_counter() - start_t

        return {
            "execution_id": f"exec_{uuid.uuid4().hex[:8]}",
            "capability_id": "identity_resolution",
            "implementation_id": "impl_challenger_identity_specialist_v2",
            "identifier": identifier,
            "documents_count": len(retrieved_docs),
            "combined_text": text_content,
            "runtime_sec": elapsed,
            "epistemic_nature": "CANDIDATE",
            "authoritative": False,
        }


class OpenSanctionsCapabilityAdapter(BaseCapabilityAdapter):
    """Wraps OpenSanctionsAdapter and OpenSanctionsSpecialist for international sanctions and offshore leaks."""

    def __init__(self, adapter: Optional[Any] = None) -> None:
        from argus.specialists.sanctions.adapter import OpenSanctionsAdapter
        self.adapter = adapter or OpenSanctionsAdapter()

    def execute(self, inputs: Dict[str, Any], corpus: Any = None) -> Dict[str, Any]:
        query = inputs.get("query") or inputs.get("entity_name", "")
        start_t = time.perf_counter()

        # Execute query via OpenSanctionsAdapter (which calls specialist and SecurityGateValidator)
        observations = self.adapter.execute_query(query)

        # Also search corpus if available
        retrieved_docs: List[Any] = []
        if corpus and hasattr(corpus, "search"):
            retrieved_docs = corpus.search(query, limit=3)

        combined_snippets = [getattr(d, "text_content", str(d)) for d in retrieved_docs]
        docs = [
            {
                "doc_id": getattr(d, "doc_id", f"doc_{i}"),
                "title": getattr(d, "title", "Corpus Document"),
                "url": getattr(d, "url", ""),
                "text": getattr(d, "text_content", str(d)),
                "source_type": getattr(d, "source_type", "sanctions_record"),
            }
            for i, d in enumerate(retrieved_docs)
        ]

        # Convert candidate observations into observation documents
        for obs in observations:
            payload = obs.payload
            entity = obs.entity_name
            ev_type = obs.evidence_type
            summary = (
                f"[{ev_type}] Entity: {entity}. Programs: {payload.get('sanctions_programs', [])}. "
                f"Authority: {payload.get('listing_authority', 'REGULATORY')}. "
                f"Details: {payload.get('program_details', payload.get('pep_role', payload.get('status', '')))}"
            )
            combined_snippets.append(summary)
            docs.append({
                "doc_id": obs.observation_id,
                "title": f"Sanctions & Offshore Record: {entity}",
                "url": f"https://www.opensanctions.org/entities/{entity.lower().replace(' ', '-')}/",
                "text": summary,
                "source_type": ev_type.lower(),
                "payload": payload,
                "confidence": obs.confidence,
                "epistemic_status": obs.epistemic_status,
                "is_authoritative": obs.is_authoritative,  # False: candidate only until verified
            })

        elapsed = time.perf_counter() - start_t
        text_content = " ".join(combined_snippets)

        return {
            "execution_id": f"exec_{uuid.uuid4().hex[:8]}",
            "capability_id": "sanctions_and_beneficial_ownership",
            "implementation_id": "impl_opensanctions_probe_v1",
            "query": query,
            "documents_count": len(docs),
            "documents": docs,
            "combined_text": text_content,
            "runtime_sec": elapsed,
            "epistemic_nature": "OBSERVATION",
            "authoritative": False,  # Candidate-only; requires Verifier
            "observations": [obs.model_dump() for obs in observations],
        }


class OnionCapabilityAdapter(BaseCapabilityAdapter):
    """Wraps UnifiedOnionAdapter for Tor hidden service and dark-web intelligence."""

    def __init__(self, adapter: Optional[Any] = None) -> None:
        from argus.specialists.onion.adapter import UnifiedOnionAdapter
        self.adapter = adapter or UnifiedOnionAdapter()
        self.implementation_id = "impl_onion_integrated_v1"

    def execute(self, inputs: Dict[str, Any], corpus: Any = None) -> Dict[str, Any]:
        query = inputs.get("query") or inputs.get("target") or inputs.get("onion_address", "")
        start_t = time.perf_counter()
        observations = self.adapter.execute_query(query)

        docs = []
        snippets = []
        for obs in observations:
            payload = obs.payload
            entity = obs.entity_name
            ev_type = obs.evidence_type
            summary = f"[{ev_type}] Service: {entity}. Status: {payload.get('status', 'ACTIVE')}. Payload: {payload}"
            snippets.append(summary)
            docs.append({
                "doc_id": obs.observation_id,
                "title": f"Onion Intelligence Record: {entity}",
                "url": f"http://{payload.get('onion_address', entity)}",
                "text": summary,
                "source_type": ev_type.lower(),
                "payload": payload,
                "confidence": obs.confidence,
                "epistemic_status": obs.epistemic_status,
                "is_authoritative": False,
            })

        elapsed = time.perf_counter() - start_t
        return {
            "execution_id": f"exec_{uuid.uuid4().hex[:8]}",
            "capability_id": "onion_intelligence",
            "implementation_id": self.implementation_id,
            "query": query,
            "documents_count": len(docs),
            "documents": docs,
            "combined_text": " ".join(snippets),
            "runtime_sec": elapsed,
            "epistemic_nature": "OBSERVATION",
            "authoritative": False,
            "observations": [obs.model_dump() for obs in observations],
        }


class AhmiaCapabilityAdapter(BaseCapabilityAdapter):
    """Wraps AhmiaSearchAdapter for Tor search & discovery."""

    def __init__(self, adapter: Optional[Any] = None) -> None:
        from argus.specialists.onion.adapter import AhmiaSearchAdapter
        self.adapter = adapter or AhmiaSearchAdapter()
        self.implementation_id = "impl_ahmia_search_v1"

    def execute(self, inputs: Dict[str, Any], corpus: Any = None) -> Dict[str, Any]:
        query = inputs.get("query") or inputs.get("target", "")
        start_t = time.perf_counter()
        observations = self.adapter.execute_query(query)
        docs = [
            {
                "doc_id": obs.observation_id,
                "title": f"Ahmia Search Record: {obs.entity_name}",
                "url": f"http://{obs.payload.get('onion_address', obs.entity_name)}",
                "text": f"[{obs.evidence_type}] {obs.payload.get('service_name')}: {obs.payload.get('description')}",
                "source_type": "onion_descriptor",
                "payload": obs.payload,
                "confidence": obs.confidence,
                "epistemic_status": obs.epistemic_status,
                "is_authoritative": False,
            }
            for obs in observations
        ]
        elapsed = time.perf_counter() - start_t
        return {
            "execution_id": f"exec_{uuid.uuid4().hex[:8]}",
            "capability_id": "onion_intelligence",
            "implementation_id": self.implementation_id,
            "query": query,
            "documents_count": len(docs),
            "documents": docs,
            "combined_text": " ".join(d["text"] for d in docs),
            "runtime_sec": elapsed,
            "epistemic_nature": "OBSERVATION",
            "authoritative": False,
            "observations": [obs.model_dump() for obs in observations],
        }


class TorBotCapabilityAdapter(BaseCapabilityAdapter):
    """Wraps TorBotCleanRoomAdapter for Tor crawling & entity extraction."""

    def __init__(self, adapter: Optional[Any] = None) -> None:
        from argus.specialists.onion.adapter import TorBotCleanRoomAdapter
        self.adapter = adapter or TorBotCleanRoomAdapter()
        self.implementation_id = "impl_torbot_crawler_v1"

    def execute(self, inputs: Dict[str, Any], corpus: Any = None) -> Dict[str, Any]:
        query = inputs.get("query") or inputs.get("onion_address", "")
        start_t = time.perf_counter()
        observations = self.adapter.execute_query(query)
        docs = [
            {
                "doc_id": obs.observation_id,
                "title": f"TorBot Crawl Record: {obs.entity_name}",
                "url": f"http://{obs.payload.get('onion_address', query)}",
                "text": f"[{obs.evidence_type}] {obs.entity_name} Crawl Payload: {obs.payload}",
                "source_type": "onion_crawl",
                "payload": obs.payload,
                "confidence": obs.confidence,
                "epistemic_status": obs.epistemic_status,
                "is_authoritative": False,
            }
            for obs in observations
        ]
        elapsed = time.perf_counter() - start_t
        return {
            "execution_id": f"exec_{uuid.uuid4().hex[:8]}",
            "capability_id": "onion_intelligence",
            "implementation_id": self.implementation_id,
            "query": query,
            "documents_count": len(docs),
            "documents": docs,
            "combined_text": " ".join(d["text"] for d in docs),
            "runtime_sec": elapsed,
            "epistemic_nature": "OBSERVATION",
            "authoritative": False,
            "observations": [obs.model_dump() for obs in observations],
        }


_CUSTOM_ADAPTERS: Dict[str, BaseCapabilityAdapter] = {}
_ADAPTER_LOCK = threading.Lock()


def register_capability_adapter(implementation_id: str, adapter: BaseCapabilityAdapter) -> None:
    """Register a custom or test capability adapter for dynamic execution."""
    if not isinstance(implementation_id, str) or not implementation_id.strip():
        raise ValueError("implementation_id must be a non-empty string.")
    if not isinstance(adapter, BaseCapabilityAdapter):
        raise TypeError(f"adapter must be an instance of BaseCapabilityAdapter, got {type(adapter).__name__}")
    with _ADAPTER_LOCK:
        _CUSTOM_ADAPTERS[implementation_id] = adapter


def unregister_capability_adapter(implementation_id: str) -> None:
    """Unregister a custom or test capability adapter."""
    with _ADAPTER_LOCK:
        _CUSTOM_ADAPTERS.pop(implementation_id, None)


def get_adapter_for_implementation(implementation_id: str, simulated: bool = False) -> BaseCapabilityAdapter:
    """Factory retrieving appropriate capability adapter by implementation ID.

    ``simulated=True`` wires specialists to the frozen benchmark corpora; it is for
    benchmark and test runs only. Live runs get real connectors (SEC EDGAR, crt.sh)
    with empty registries, and corpus-only specialists report that no live source exists.
    """
    with _ADAPTER_LOCK:
        if implementation_id in _CUSTOM_ADAPTERS:
            return _CUSTOM_ADAPTERS[implementation_id]

    adapters: Dict[str, BaseCapabilityAdapter] = {
        "impl_argus_generalist_v1": ArgusResearchAdapter(),
        "impl_identity_probe_specialist_v1": IdentitySpecialistAdapter(simulated=simulated),
        "impl_infrastructure_probe_specialist_v1": InfrastructureSpecialistAdapter(simulated=simulated),
        "impl_corporate_registry_specialist_v1": CorporateSpecialistAdapter(simulated=simulated),
        "impl_challenger_identity_specialist_v2": ChallengerIdentityAdapter(),
    }
    if simulated:
        adapters.update({
            "impl_opensanctions_probe_v1": OpenSanctionsCapabilityAdapter(),
            "impl_onion_integrated_v1": OnionCapabilityAdapter(),
            "impl_ahmia_search_v1": AhmiaCapabilityAdapter(),
            "impl_torbot_crawler_v1": TorBotCapabilityAdapter(),
        })
    else:
        adapters.update({
            "impl_opensanctions_probe_v1": NoLiveSourceAdapter("impl_opensanctions_probe_v1", "sanctions screening"),
            "impl_onion_integrated_v1": NoLiveSourceAdapter("impl_onion_integrated_v1", "onion service intelligence"),
            "impl_ahmia_search_v1": NoLiveSourceAdapter("impl_ahmia_search_v1", "onion search"),
            "impl_torbot_crawler_v1": NoLiveSourceAdapter("impl_torbot_crawler_v1", "onion crawling"),
        })

    # Vertical 6: Email & Account Intelligence Adapters
    if implementation_id == "impl_email_to_account_discovery_v1":
        from argus.specialists.email.adapter import EmailToAccountDiscoveryAdapter
        return EmailToAccountDiscoveryAdapter()
    elif implementation_id == "impl_identity_to_email_discovery_v1":
        from argus.specialists.email.adapter import IdentityToEmailDiscoveryAdapter
        return IdentityToEmailDiscoveryAdapter()
    elif implementation_id == "impl_email_address_verification_v1":
        from argus.specialists.email.adapter import EmailVerificationAdapter
        return EmailVerificationAdapter()
    elif implementation_id == "impl_email_identity_resolution_v1":
        from argus.specialists.email.adapter import EmailIdentityResolutionAdapter
        return EmailIdentityResolutionAdapter()
    elif implementation_id == "impl_email_account_specialist_v1":
        from argus.specialists.email.adapter import EmailAccountSpecialistAdapter
        return EmailAccountSpecialistAdapter()

    if implementation_id not in adapters:
        raise KeyError(f"No registered adapter for implementation '{implementation_id}'")
    return adapters[implementation_id]
