"""Diagram Agent — deterministic, no LLM.

Wraps :class:`MermaidRenderer` to fit the agent interface used by the
workflow. Keeping it as an "agent" preserves a uniform invocation
contract (input model → output model) without invoking the LLM.
"""

from __future__ import annotations

from backend.agents.base import AgentContext, BaseAgent
from backend.domain.models.artifacts import DiagramArtifact
from backend.domain.models.ir import RelationalModel
from backend.services.llm.gemini import GeminiService
from backend.services.rendering.mermaid import MermaidRenderer


class DiagramAgent(BaseAgent[RelationalModel, DiagramArtifact]):
    name = "diagram"
    output_schema = DiagramArtifact

    def __init__(self, llm: GeminiService, renderer: MermaidRenderer) -> None:
        super().__init__(llm)
        self._renderer = renderer

    # The deterministic path overrides ``run`` and skips the LLM.
    async def run(
        self,
        payload: RelationalModel,
        ctx: AgentContext,
    ) -> DiagramArtifact:
        self._logger.info("agent.run.start", session_id=ctx.session_id)
        artifact = self._renderer.render(payload)
        self._logger.info(
            "agent.run.done",
            session_id=ctx.session_id,
            tables=len(payload.tables),
        )
        return artifact

    # Required by the abstract base class even though unused here.
    def build_system_prompt(self) -> str:  # pragma: no cover
        return ""

    def build_user_prompt(self, payload: RelationalModel) -> str:  # pragma: no cover
        return ""
