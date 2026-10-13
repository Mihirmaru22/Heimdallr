"""System 1 Non-Autoregressive Decision Engine for Argus.

Powered by Laya (convaiinnovations/laya), providing single-forward-pass (~33ms)
zero-shot typed decisions (choice, score, noul/binary) across 100+ languages.

Used as a fast cognitive filter for:
  1. Search Snippet Triage & Ranking (before downloading full web pages)
  2. Document Relevance & Boilerplate Gating (filtering 80% junk before calling slow LLMs)
  3. Search Archetype Routing (newsroom vs. regulatory vs. directory vs. technical)
  4. Task Difficulty & Scope Calibration (dynamic budgeting across any domain)
"""

import logging
from typing import Any

from argus.domain.task import ResearchTask
from argus.search.models import SearchResult

logger = logging.getLogger(__name__)


class System1DecisionEngine:
    """Non-autoregressive System 1 decision engine for real-time triage and routing."""

    def __init__(self, preload: bool = False, model_override: str | None = None) -> None:
        self._router = None
        self._preload = preload
        self._model_override = model_override
        self._is_available: bool | None = None

        if preload:
            self._ensure_router()

    def _ensure_router(self) -> Any:
        """Lazily initialize the Laya Router on first invocation."""
        if self._is_available is False:
            return None
        if self._router is not None:
            return self._router

        try:
            from laya import Router

            logger.info("Initializing Laya System 1 Decision Router...")
            self._router = Router(preload=self._preload)
            self._is_available = True
            logger.info("Laya System 1 Decision Router initialized successfully.")
            return self._router
        except Exception as exc:
            logger.warning(
                "Laya decision engine could not be initialized (%s). Falling back to heuristic mode.",
                exc,
            )
            self._is_available = False
            return None

    @property
    def is_available(self) -> bool:
        """Check if Laya decision router is ready."""
        if self._is_available is None:
            self._ensure_router()
        return bool(self._is_available)

    def triage_search_results(
        self,
        results: list[SearchResult],
        objective_target: str,
        task_title: str,
        top_k: int = 3,
        threshold: float = 0.40,
    ) -> list[SearchResult]:
        """Score and filter search snippets using fast single-pass decisions.

        Ranks URLs by relevance probability in ~33ms without calling heavy LLMs.
        """
        if not results:
            return []

        router = self._ensure_router()
        if router is None:
            # Fallback: preserve original search provider order
            return results[:top_k]

        scored_results: list[tuple[float, SearchResult]] = []

        questions = {
            "relevance": {
                "type": "noul",
                "instructions": (
                    f"Does this search snippet contain factual or operational details "
                    f"relevant to '{task_title}' concerning '{objective_target}'?"
                ),
            }
        }

        for item in results:
            snippet_text = f"Title: {item.title}\nSnippet: {item.snippet}\nURL: {item.url}"
            try:
                kwargs: dict[str, Any] = {}
                if self._model_override:
                    kwargs["model"] = self._model_override

                prediction = router.predict(snippet_text, questions, **kwargs)
                prob = float(
                    prediction.get("answers", {}).get("relevance", {}).get("noul", 0.5)
                )
                scored_results.append((prob, item))
            except Exception as exc:
                logger.debug("Laya snippet triage failed for '%s': %s", item.url, exc)
                scored_results.append((0.5, item))

        # Sort by relevance probability descending
        scored_results.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored_results[:top_k]]

    @staticmethod
    def infer_document_boilerplate_heuristic(doc_text: str) -> tuple[bool, str]:
        """Fast heuristic (~0.05ms) to catch 404s, login walls, and empty cookie boilerplate."""
        sample = doc_text[:2500].strip().lower()
        if not sample:
            return True, "empty"

        # Explicit error and challenge indicators
        error_indicators = (
            "404 not found",
            "page not found",
            "403 forbidden",
            "access denied",
            "cloudflare",
            "just a moment...",
            "checking your browser",
            "please enable cookies",
            "attention required! | cloudflare",
            "sign in to linkedin",
            "join linkedin to view full profile",
            "you need to sign in",
            "log in to see more",
        )
        if any(ind in sample for ind in error_indicators):
            return True, "boilerplate"

        # Dominant cookie consent banner with zero substantive content
        cookie_indicators = (
            "we use cookies to give you the best experience",
            "accept all cookies",
            "manage cookie preferences",
            "cookie policy | privacy policy",
        )
        if any(ci in sample for ci in cookie_indicators) and len(sample) < 400:
            return True, "boilerplate"

        return False, "factual"

    def triage_document(
        self,
        doc_text: str,
        task_title: str,
        objective_target: str,
    ) -> tuple[bool, float, str]:
        """Fast gatekeeper to discard 404s, cookie banners, and noise in ~33ms.

        Returns (is_relevant, confidence, content_type).
        """
        # 1. Fast deterministic heuristic pre-pass (<0.1ms)
        is_bp, reason = self.infer_document_boilerplate_heuristic(doc_text)
        if is_bp:
            return False, 0.95, reason

        router = self._ensure_router()
        if router is None:
            # Fallback: allow document to pass to Worker LLM
            return True, 1.0, "unfiltered"

        sample = doc_text[:3000].strip()
        if len(sample) < 50:
            return False, 0.99, "boilerplate"

        questions = {
            "substantive": {
                "type": "noul",
                "instructions": (
                    f"Does this text provide substantive factual information or data "
                    f"addressing '{task_title}' regarding '{objective_target}'?"
                ),
            },
            "category": {
                "type": "choice",
                "instructions": "What category best describes this document?",
                "criteria": {
                    "factual": "factual report, operational profile, directory, news, technical data",
                    "boilerplate": "cookie consent, 404 error, login wall, terms of service, empty menu",
                    "promotional": "marketing slogans and puffery without concrete factual data",
                },
            },
        }

        try:
            kwargs: dict[str, Any] = {}
            if self._model_override:
                kwargs["model"] = self._model_override

            res = router.predict(sample, questions, **kwargs)
            prob = float(res.get("answers", {}).get("substantive", {}).get("noul", 0.5))
            cat = str(res.get("answers", {}).get("category", {}).get("choice", "factual"))

            if cat == "boilerplate":
                return False, 0.90, "boilerplate"

            return True, prob, cat
        except Exception as exc:
            logger.debug("Laya document triage error: %s", exc)
            return True, 0.5, "unfiltered"

    @staticmethod
    def infer_archetype_heuristic(text: str) -> str:
        """Domain-agnostic archetype classifier fallback based on syntactic intent."""
        import re

        text_lower = text.lower()
        words = set(re.findall(r"[a-z0-9_]+", text_lower))

        # Regulatory / permits / compliance / legal inspection
        reg_words = {
            "regulatory", "permit", "permits", "license", "licenses", "compliance",
            "inspection", "inspections", "osha", "epa", "fda", "sec", "violation",
            "violations", "filing", "filings", "audit", "audits", "standard", "standards"
        }
        if (words & reg_words) or ("regulatory filing" in text_lower) or ("cgmp" in text_lower):
            return "regulatory"

        # Leadership / personnel / appointments
        leadership_words = {
            "leadership", "personnel", "head", "heads", "manager", "managers",
            "director", "directors", "lead", "leads", "officer", "officers",
            "executive", "executives", "appointment", "appointments", "appointed",
            "promoted", "chief", "investigator", "investigators", "superintendent",
            "superintendents", "staff", "management"
        }
        if (words & leadership_words) or ("who is" in text_lower) or ("contact person" in text_lower):
            return "newsroom"

        # Directory / facilities / sites / plants / locations
        dir_words = {
            "facility", "facilities", "site", "sites", "plant", "plants",
            "factory", "factories", "mine", "mines", "refinery", "refineries",
            "directory", "directories", "location", "locations", "address",
            "switchboard", "registry", "hub", "headquarters", "center", "campus"
        }
        if (words & dir_words) or ("supplier registry" in text_lower):
            return "directory"

        # Technical / specifications
        tech_words = {
            "specification", "specifications", "spec", "specs", "patent", "patents",
            "architecture", "manual", "manuals", "datasheet", "datasheets", "protocol",
            "protocols", "formula", "blueprint", "cad"
        }
        if words & tech_words:
            return "technical"

        return "general"

    def classify_search_archetype(
        self,
        task_title: str,
        task_description: str,
        objective_target: str,
    ) -> str:
        """Dynamically determine optimal search archetype for ANY domain."""
        router = self._ensure_router()
        if router is None:
            return self.infer_archetype_heuristic(
                f"{task_title} {task_description} {objective_target}"
            )

        state = (
            f"Target Domain: {objective_target}\n"
            f"Task: {task_title}\n"
            f"Description: {task_description}"
        )

        questions = {
            "archetype": {
                "type": "choice",
                "instructions": "What information source archetype is most likely to contain this data?",
                "criteria": {
                    "newsroom": "personnel leadership, plant managers, site directors, executive appointments, promotions, press releases",
                    "regulatory": "compliance records, permits, SEC/OSHA/EPA filings, government databases",
                    "directory": "plant locations, facility lists, site addresses, corporate contact pages, supplier registries",
                    "technical": "specifications, engineering manuals, patents, academic research",
                    "general": "encyclopedia overviews, industry summaries, general news",
                },
            }
        }

        try:
            kwargs: dict[str, Any] = {}
            if self._model_override:
                kwargs["model"] = self._model_override

            res = router.predict(state, questions, **kwargs)
            choice = str(res.get("answers", {}).get("archetype", {}).get("choice", "general"))
            if choice in ("newsroom", "regulatory", "directory", "technical", "general"):
                return choice
            return self.infer_archetype_heuristic(
                f"{task_title} {task_description} {objective_target}"
            )
        except Exception as exc:
            logger.debug("Laya archetype routing error: %s", exc)
            return self.infer_archetype_heuristic(
                f"{task_title} {task_description} {objective_target}"
            )

    def estimate_task_difficulty(
        self,
        objective_goal: str,
    ) -> tuple[int, int]:
        """Estimate topic obscurity and return recommended (budget_tasks, crawl_per_task)."""
        router = self._ensure_router()
        if router is None:
            return 12, 3

        questions = {
            "difficulty": {
                "type": "score",
                "instructions": "How obscure, private, or difficult to find is this information likely to be?",
                "criteria": [
                    "easy: readily public high-level corporate facts (CEOs, headquarters)",
                    "medium: operational details (assembly plants, product models, regional sites)",
                    "hard: specific personnel, unlisted plant managers, technical leads, direct contact info",
                ],
            }
        }

        try:
            kwargs: dict[str, Any] = {}
            if self._model_override:
                kwargs["model"] = self._model_override

            res = router.predict(objective_goal, questions, **kwargs)
            score = int(res.get("answers", {}).get("difficulty", {}).get("score", 1))

            if score == 0:
                return 6, 2
            elif score == 1:
                return 12, 3
            else:
                return 20, 4
        except Exception:
            return 12, 3

    @staticmethod
    def infer_priority_heuristic(
        task_title: str,
        task_description: str = "",
        required_fields: list[str] | None = None,
    ) -> int:
        """Domain-agnostic priority heuristic fallback when Laya router is unavailable."""
        text_lower = f"{task_title} {task_description}".lower()

        # Secondary trivia: postal, municipal borders, tax parcel checks on disambiguation
        trivia_words = {
            "boundary", "municipal", "jurisdiction", "city limits", "township",
            "county", "postal", "parcel", "tax search", "coordinates", "zip code"
        }
        if any(w in text_lower for w in trivia_words) and "disambiguate" in text_lower:
            return 3

        # Urgent: direct investigation of leadership, personnel, and contact info
        urgent_words = {
            "director", "manager", "head", "lead", "phone", "email",
            "contact", "personnel", "chief engineer", "switchboard"
        }
        if any(w in text_lower for w in urgent_words):
            return 10

        return 7

    def score_task_priority(
        self,
        task_title: str,
        task_description: str = "",
        objective_goal: str = "",
        required_fields: list[str] | None = None,
    ) -> int:
        """Neural dynamic task priority scorer powered by Laya (~33ms).

        Evaluates semantic urgency against the user's intelligence goal:
          - 10: Urgent (directly investigates target leadership, plant directors, technical leads, contacts)
          - 7:  Primary (discovers manufacturing plants, facilities, operational status, factory footprint)
          - 3:  Deprioritized (secondary disambiguation of municipal borders, postal definitions, coordinates)
        """
        router = self._ensure_router()
        if router is None:
            return self.infer_priority_heuristic(task_title, task_description, required_fields)

        state = (
            f"Goal: {objective_goal}\n"
            f"Required Fields: {', '.join(required_fields or [])}\n"
            f"Task: {task_title}\n"
            f"Description: {task_description}"
        )

        questions = {
            "priority_level": {
                "type": "choice",
                "instructions": f"Goal: {objective_goal}. Rate the execution urgency of this task.",
                "criteria": {
                    "urgent": "directly investigates or verifies target leadership, plant directors, engineering leads, or direct contacts",
                    "primary": "discovers manufacturing plants, facilities, operational status, factory footprint, or initial mapping",
                    "deprioritized": "secondary disambiguation of municipal borders, postal definitions, geographic coordinates, or tax parcels",
                },
            }
        }

        try:
            kwargs: dict[str, Any] = {}
            if self._model_override:
                kwargs["model"] = self._model_override
            res = router.predict(state, questions, **kwargs)
            choice = str(res.get("answers", {}).get("priority_level", {}).get("choice", "primary"))
            if choice == "urgent":
                return 10
            elif choice == "primary":
                return 7
            elif choice == "deprioritized":
                return 3
            return 7
        except Exception as exc:
            logger.debug("Laya task priority scoring error: %s", exc)
            return self.infer_priority_heuristic(task_title, task_description, required_fields)

    def calibrate_budget_and_depth(
        self,
        objective_target: str,
        intelligence_goal: str,
        required_fields: list[str] | None = None,
    ) -> tuple[int, int]:
        """Dynamically determine optimal (max_tasks, max_depth) up to 50 tasks and depth 5."""
        router = self._ensure_router()
        if router is None:
            return 50, 5

        state = (
            f"Target: {objective_target}\n"
            f"Goal: {intelligence_goal}\n"
            f"Required Fields: {', '.join(required_fields or [])}"
        )

        questions = {
            "scope": {
                "type": "choice",
                "instructions": "Determine the optimal multi-turn task budget and epistemic depth.",
                "criteria": {
                    "exhaustive": "multi-facility industrial investigation requiring plant-by-plant probing, leadership succession tracking, and contact resolution (budget: 50 tasks, depth: 5)",
                    "targeted": "focused enterprise analysis or single facility deep dive (budget: 30-35 tasks, depth: 4)",
                    "overview": "high-level corporate summary, CEO, headquarters (budget: 10-15 tasks, depth: 2-3)",
                },
            }
        }

        try:
            kwargs: dict[str, Any] = {}
            if self._model_override:
                kwargs["model"] = self._model_override
            res = router.predict(state, questions, **kwargs)
            choice = str(res.get("answers", {}).get("scope", {}).get("choice", "exhaustive"))
            if choice == "exhaustive":
                return 50, 5
            elif choice == "targeted":
                return 35, 4
            else:
                return 15, 3
        except Exception:
            return 50, 5

    @staticmethod
    def infer_branch_depth_heuristic(
        task_title: str,
        task_description: str = "",
        current_depth: int = 1,
        max_depth: int = 5,
    ) -> bool:
        """Domain-agnostic branch depth heuristic fallback."""
        if current_depth > max_depth:
            return False
        if current_depth < 2:
            return True

        text_lower = f"{task_title} {task_description}".lower()
        if (
            any(
                w in text_lower
                for w in [
                    "boundary", "municipal", "township", "county",
                    "tax parcel", "postal", "parcel", "city limits"
                ]
            )
            and current_depth >= 2
        ):
            return False
        return True

    def should_branch_deeper(
        self,
        task_title: str,
        task_description: str = "",
        current_depth: int = 1,
        max_depth: int = 5,
        objective_goal: str = "",
    ) -> bool:
        """Dynamically decide whether a specific task branch should recurse deeper (~33ms).

        Allows depth up to 5 for personnel succession, direct contacts, and plant status.
        Halts shallow (depth <= 2 or 3) for secondary municipal borders, tax maps, and postal trivia.
        """
        if current_depth > max_depth:
            return False

        # If at depth 1, always allow initial discovery fan-out
        if current_depth < 2:
            return True

        router = self._ensure_router()
        if router is None:
            return self.infer_branch_depth_heuristic(
                task_title, task_description, current_depth, max_depth
            )

        state = (
            f"Goal: {objective_goal}\n"
            f"Current Depth: {current_depth}\n"
            f"Task: {task_title}\n"
            f"Description: {task_description}"
        )

        questions = {
            "should_branch_deeper": {
                "type": "choice",
                "instructions": f"Goal: {objective_goal}. Should the research agent spawn deeper recursive subtasks for this topic?",
                "criteria": {
                    "allow_deep": "critical personnel succession, direct contact discovery, operational plant status (allow up to depth 5)",
                    "halt_shallow": "secondary municipal borders, tax maps, postal definitions, historical trivia (halt branch depth)",
                },
            }
        }

        try:
            kwargs: dict[str, Any] = {}
            if self._model_override:
                kwargs["model"] = self._model_override
            res = router.predict(state, questions, **kwargs)
            choice = str(
                res.get("answers", {})
                .get("should_branch_deeper", {})
                .get("choice", "allow_deep")
            )
            return choice == "allow_deep"
        except Exception as exc:
            logger.debug("Laya should_branch_deeper error: %s", exc)
            return self.infer_branch_depth_heuristic(
                task_title, task_description, current_depth, max_depth
            )


