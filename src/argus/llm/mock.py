from typing import Any, TypeVar

from pydantic import BaseModel

from argus.llm.provider import LLMProvider

T = TypeVar("T", bound=BaseModel)


class MockLLMProvider(LLMProvider):
    """Mock LLM provider returning predefined Pydantic models for testing."""

    def __init__(
        self,
        responses: list[BaseModel] | None = None,
        default_response: BaseModel | None = None,
    ) -> None:
        self.responses = list(responses) if responses else []
        self.default_response = default_response
        self.calls: list[dict[str, Any]] = []

    async def generate_structured(
        self,
        prompt: str,
        response_model: type[T],
        system_prompt: str | None = None,
        temperature: float = 0.0,
    ) -> T:
        self.calls.append(
            {
                "prompt": prompt,
                "response_model": response_model,
                "system_prompt": system_prompt,
                "temperature": temperature,
            }
        )

        # Check if there is a response in the queue matching the requested type
        for i, resp in enumerate(self.responses):
            if isinstance(resp, response_model):
                return self.responses.pop(i)  # type: ignore[return-value]

        if self.default_response is not None and isinstance(
            self.default_response, response_model
        ):
            return self.default_response  # type: ignore[return-value]

        raise ValueError(
            f"MockLLMProvider has no configured response for model {response_model.__name__}. "
            f"Available responses: {[type(r).__name__ for r in self.responses]}"
        )
