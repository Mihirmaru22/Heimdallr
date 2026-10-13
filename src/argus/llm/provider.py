from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMProvider(ABC):
    """Abstract interface for LLM calls enforcing structured Pydantic outputs."""

    @abstractmethod
    async def generate_structured(
        self,
        prompt: str,
        response_model: type[T],
        system_prompt: str | None = None,
        temperature: float = 0.0,
    ) -> T:
        """Call LLM and parse the response strictly into the requested Pydantic model."""
