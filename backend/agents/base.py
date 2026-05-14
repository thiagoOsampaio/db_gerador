"""Base agent abstraction.

All agents:
- receive the Gemini service via constructor (DI),
- never touch credentials, raw connection strings, or API keys,
- declare an explicit output schema and return a Pydantic instance,
- isolate prompt construction in their own module (no business logic in
  prompts, no prompts inside the workflow layer).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, TypeVar

from pydantic import BaseModel

from backend.domain.exceptions import AgentExecutionError
from backend.observability.logging import get_logger
from backend.services.llm.gemini import GeminiService

TInput = TypeVar("TInput", bound=BaseModel)
TOutput = TypeVar("TOutput", bound=BaseModel)


@dataclass(frozen=True)
class AgentContext:
    """Sanitized context shared with every agent invocation."""

    session_id: str
    user_email: str


class BaseAgent(ABC, Generic[TInput, TOutput]):
    """Abstract base for all specialized agents."""

    name: str = "base"
    output_schema: type[BaseModel]

    def __init__(self, llm: GeminiService) -> None:
        self._llm = llm
        self._logger = get_logger(f"agent.{self.name}")

    @abstractmethod
    def build_system_prompt(self) -> str:
        """Return the static system prompt for this agent."""

    @abstractmethod
    def build_user_prompt(self, payload: TInput) -> str:
        """Render the structured input into a sanitized user prompt."""

    async def run(self, payload: TInput, ctx: AgentContext) -> TOutput:
        self._logger.info("agent.run.start", session_id=ctx.session_id)
        try:
            result = await self._llm.invoke_structured(
                system_prompt=self.build_system_prompt(),
                user_prompt=self.build_user_prompt(payload),
                output_schema=self.output_schema,  # type: ignore[arg-type]
            )
        except Exception as exc:
            self._logger.error(
                "agent.run.error",
                session_id=ctx.session_id,
                error=type(exc).__name__,
            )
            raise AgentExecutionError(self.name, str(exc)) from exc

        self._logger.info("agent.run.done", session_id=ctx.session_id)
        return result  # type: ignore[return-value]
