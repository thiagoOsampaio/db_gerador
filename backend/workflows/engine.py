"""High-level workflow facade used by the API layer.

Wraps the compiled LangGraph instance with convenience methods for:
- starting a new analysis (``start``)
- approving / rejecting at the human-in-the-loop gate (``approve`` /
  ``reject``)
- inspecting current state (``get_state``)

This shields routes from LangGraph-specific configuration details.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from langgraph.pregel import Pregel

from backend.domain.enums import ApprovalState
from backend.domain.exceptions import InvalidApprovalStateError


class WorkflowEngine:
    def __init__(self, graph: Pregel) -> None:
        self._graph = graph

    @staticmethod
    def _config(session_id: UUID | str) -> dict[str, Any]:
        return {"configurable": {"thread_id": str(session_id)}}

    async def start(
        self,
        *,
        session_id: UUID,
        user_email: str,
        openproject_task_id: str,
        developer_request: str | None = None,
        framework_name: str | None = None,
        orm_name: str | None = None,
        project_metadata: dict[str, Any] | None = None,
        user_entities: list[str] | None = None,
        user_relationships: list[str] | None = None,
        is_retake: bool = False,
        parent_session_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Kick off the workflow; runs until the approval interrupt."""
        initial = {
            "session_id": str(session_id),
            "user_email": user_email,
            "openproject_task_id": openproject_task_id,
            "developer_request": developer_request,
            "openproject_task_description": None,
            "framework_name": framework_name,
            "orm_name": orm_name,
            "project_metadata": project_metadata or {},
            "user_entities": user_entities or [],
            "user_relationships": user_relationships or [],
            "performance_recommendations": [],
            "security_recommendations": [],
            "errors": [],
            "is_retake": is_retake,
            "parent_session_id": (
                str(parent_session_id) if parent_session_id else None
            ),
        }
        return await self._graph.ainvoke(initial, self._config(session_id))

    async def approve(self, session_id: UUID) -> dict[str, Any]:
        state = await self._graph.aget_state(self._config(session_id))
        if not state:
            raise InvalidApprovalStateError(f"No active workflow for {session_id}")
        await self._graph.aupdate_state(
            self._config(session_id),
            {"approval_state": ApprovalState.APPROVED},
            as_node="await_approval",
        )
        return await self._graph.ainvoke(None, self._config(session_id))

    async def reject(self, session_id: UUID, feedback: str | None) -> dict[str, Any]:
        await self._graph.aupdate_state(
            self._config(session_id),
            {
                "approval_state": ApprovalState.REJECTED,
                "rejection_feedback": feedback,
            },
            as_node="await_approval",
        )
        return await self._graph.ainvoke(None, self._config(session_id))

    async def get_state(self, session_id: UUID) -> dict[str, Any] | None:
        state = await self._graph.aget_state(self._config(session_id))
        return state.values if state else None
