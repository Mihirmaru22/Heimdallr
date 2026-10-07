"""Base interface for Research Brain executive planners."""

from abc import ABC, abstractmethod
from typing import Any

from argus.brain.models import ResearchDossier, StoppingEvaluation
from argus.domain.objective import ResearchObjective
from argus.domain.task import ResearchTask


class BaseResearchBrain(ABC):
    """Abstract interface defining the Research Brain contract."""

    @abstractmethod
    async def plan_initial_tasks(
        self, objective: ResearchObjective
    ) -> list[ResearchTask]:
        """Decompose a ResearchObjective into initial executable tasks."""
        pass

    @abstractmethod
    def extract_search_queries(
        self,
        task: ResearchTask,
        objective_target: str = "",
        dork: bool | None = None,
    ) -> list[str]:
        """Parse search queries and optionally apply search dorking."""
        pass

    @abstractmethod
    def evaluate_stopping_criteria(
        self,
        objective: ResearchObjective,
        tasks_executed: int,
    ) -> StoppingEvaluation:
        """Evaluate if research should terminate based on budget or epistemic satisfaction."""
        pass

    @abstractmethod
    async def plan_followup_tasks(
        self,
        objective: ResearchObjective,
        missing_fields: list[str],
        disambiguation_tasks: list[str],
        parent_task: ResearchTask | None = None,
    ) -> list[ResearchTask]:
        """Create targeted follow-up tasks for missing fields or contradictions."""
        pass

    @abstractmethod
    async def synthesize_dossier(
        self,
        objective: ResearchObjective,
        total_tasks: int,
        total_documents: int,
    ) -> ResearchDossier:
        """Synthesize all verified evidence into a final ResearchDossier."""
        pass
