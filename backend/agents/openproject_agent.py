"""OpenProject Agent — orchestrates task comment + attachments + transition.

This agent is LLM-free: it builds a markdown summary deterministically
from the analysis result and invokes the OpenProject service layer.
The API token is supplied per-request inside the input payload and is
never persisted in plaintext or logged.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, SecretStr

from backend.agents.base import AgentContext, BaseAgent
from backend.domain.models.analysis import AnalysisResult
from backend.domain.models.openproject import (
    OpenProjectTaskUpdate,
    TaskAttachment,
    TaskComment,
)
from backend.services.llm.gemini import GeminiService
from backend.services.openproject.attachment_service import OpenProjectAttachmentService
from backend.services.openproject.client import OpenProjectClient
from backend.services.openproject.task_service import OpenProjectTaskService


class OpenProjectAgentInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    task_id: str
    user_email: str
    openproject_token: SecretStr
    result: AnalysisResult


class OpenProjectAgent(BaseAgent[OpenProjectAgentInput, OpenProjectTaskUpdate]):
    name = "openproject"
    output_schema = OpenProjectTaskUpdate

    def __init__(
        self,
        llm: GeminiService,
        *,
        api_url: str,
        timeout: int = 30,
        completion_status_id: int | None = None,
    ) -> None:
        super().__init__(llm)
        self._api_url = api_url
        self._timeout = timeout
        self._completion_status_id = completion_status_id

    async def run(
        self,
        payload: OpenProjectAgentInput,
        ctx: AgentContext,
    ) -> OpenProjectTaskUpdate:
        self._logger.info("agent.run.start", session_id=ctx.session_id)
        comment_body = self._render_comment_markdown(
            payload.user_email,
            payload.result,
        )

        # Per-request client built from the user-supplied token.
        async with OpenProjectClient(
            api_url=self._api_url,
            token=payload.openproject_token,
            timeout=self._timeout,
        ) as client:
            tasks = OpenProjectTaskService(client)
            attachments_svc = OpenProjectAttachmentService(client)

            attachments: list[TaskAttachment] = []
            if payload.result.diagram:
                attachments.append(
                    await attachments_svc.upload(
                        work_package_id=payload.task_id,
                        filename="erd.mmd",
                        content=payload.result.diagram.content.encode("utf-8"),
                        content_type="text/plain",
                        description="Mermaid ER diagram",
                    )
                )
            if payload.result.sql_artifact:
                attachments.append(
                    await attachments_svc.upload(
                        work_package_id=payload.task_id,
                        filename="migration.sql",
                        content=payload.result.sql_artifact.ddl.encode("utf-8"),
                        content_type="application/sql",
                        description="Generated SQL DDL",
                    )
                )

            try:
                await tasks.add_comment(payload.task_id, comment_body)
            except Exception as exc:  # noqa: BLE001
                self._logger.warning("openproject.comment_failed", error=str(exc))
                return OpenProjectTaskUpdate(
                    task_id=payload.task_id,
                    attachments=attachments,
                    success=False,
                    error=f"comment_failed: {type(exc).__name__}",
                )

            status_transition: str | None = None
            if self._completion_status_id is not None:
                try:
                    wp = await tasks.get_work_package(payload.task_id)
                    lock_version = int(wp.get("lockVersion", 0))
                    await tasks.transition_status(
                        payload.task_id, self._completion_status_id, lock_version
                    )
                    status_transition = str(self._completion_status_id)
                except Exception as exc:  # noqa: BLE001
                    self._logger.warning("openproject.status_failed", error=str(exc))

        self._logger.info("agent.run.done", session_id=ctx.session_id)
        return OpenProjectTaskUpdate(
            task_id=payload.task_id,
            comment=TaskComment(body=comment_body, author_email=payload.user_email),
            attachments=attachments,
            status_transition=status_transition,
            success=True,
        )

    # Required by the abstract base class even though unused here.
    def build_system_prompt(self) -> str:  # pragma: no cover
        return ""

    def build_user_prompt(self, payload: OpenProjectAgentInput) -> str:  # pragma: no cover
        return ""

    @staticmethod
    def _render_comment_markdown(user_email: str, result: AnalysisResult) -> str:
        perf = result.performance_recommendations
        sec = result.security_recommendations
        lines: list[str] = [
            "## db_gerador — Database Architecture Analysis",
            "",
            f"Requested by: {user_email}",
            "",
        ]

        if result.diagram:
            lines.extend(
                [
                    "### ER Diagram (Mermaid)",
                    "",
                    "```mermaid",
                    result.diagram.content,
                    "```",
                    "",
                ]
            )

        lines.extend(_render_recommendation_section("Performance", perf))
        lines.extend(_render_recommendation_section("Security", sec))

        if result.sql_artifact:
            lines.extend(
                [
                    "### SQL Migration (PostgreSQL)",
                    "",
                    "See attached `migration.sql`.",
                    f"Summary: {result.sql_artifact.summary or 'n/a'}",
                    "",
                ]
            )

        return "\n".join(lines)

    def build_system_prompt(self) -> str:
        raise NotImplementedError

    def build_user_prompt(self, payload: OpenProjectAgentInput) -> str:
        raise NotImplementedError



def _render_recommendation_section(title: str, items: list) -> list[str]:  # type: ignore[type-arg]
    if not items:
        return [f"### {title} Recommendations", "", "_No recommendations._", ""]
    out = [f"### {title} Recommendations", ""]
    for r in items:
        sev = getattr(r, "severity", "info")
        out.append(f"- **[{sev}]** {r.title}: {r.description}")
    out.append("")
    return out
