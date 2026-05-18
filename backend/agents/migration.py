from __future__ import annotations

from pydantic import BaseModel

from backend.agents.base import AgentContext, BaseAgent
from backend.domain.models.artifacts import MigrationPlan, SqlArtifact
from backend.domain.models.ir import RelationalModel
from backend.services.llm.gemini import GeminiService
from backend.services.rendering.sql_generator import SqlGenerator


class MigrationOutput(BaseModel):
    sql_artifact: SqlArtifact
    migration_plan: MigrationPlan


class MigrationAgent(BaseAgent[RelationalModel, MigrationOutput]):
    name = "migration"
    output_schema = MigrationOutput

    def __init__(
        self,
        llm: GeminiService,
        generator: SqlGenerator,
        *,
        emit_alembic: bool = True,
    ) -> None:
        super().__init__(llm)
        self._generator = generator
        self._emit_alembic = emit_alembic

    async def run(
        self,
        payload: RelationalModel,
        ctx: AgentContext,
    ) -> MigrationOutput:
        self._logger.info("agent.run.start", session_id=ctx.session_id)
        artifact, plan = self._generator.generate(
            payload, emit_alembic=self._emit_alembic
        )
        self._logger.info(
            "agent.run.done",
            session_id=ctx.session_id,
            tables=len(payload.tables),
            steps=len(plan.steps),
        )
        return MigrationOutput(sql_artifact=artifact, migration_plan=plan)

    def build_system_prompt(self) -> str:  # pragma: no cover
        return ""

    def build_user_prompt(self, payload: RelationalModel) -> str:  # pragma: no cover
        return ""
