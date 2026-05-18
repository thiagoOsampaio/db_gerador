"""LangGraph workflow state.

This is the single source of truth carried between nodes. It NEVER
contains plaintext credentials, API keys, tokens, or hostnames+ports
combined with usernames. Customer credentials are accessed exclusively
through the encrypted-credential repository, keyed by ``session_id``.
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages  # noqa: F401  (kept for users who add chat history)

from backend.domain.enums import AnalysisStatus, ApprovalState
from backend.domain.models.artifacts import (
    DiagramArtifact,
    MigrationPlan,
    SqlArtifact,
)
from backend.domain.models.ir import ProjectIR, RelationalModel
from backend.domain.models.openproject import OpenProjectTaskUpdate
from backend.domain.models.recommendations import (
    PerformanceRecommendation,
    SecurityRecommendation,
)
from backend.domain.models.schema import Schema


def _merge_list(left: list, right: list) -> list:  # type: ignore[type-arg]
    """Reducer for fields populated by parallel branches."""
    return [*left, *right]


def _merge_errors(left: list[str], right: list[str]) -> list[str]:
    return [*left, *right]


class WorkflowState(TypedDict, total=False):
    """LangGraph state for the database-analysis workflow."""

    # Identity / request metadata (no secrets)
    session_id: str
    user_email: str
    openproject_task_id: str

    # Inputs supplied by the API caller (already sanitized)
    framework_name: str | None
    orm_name: str | None
    project_metadata: dict[str, object]
    user_entities: list[str]
    user_relationships: list[str]
    # Authoritative natural-language requirement: the developer's own
    # request plus the description fetched from the OpenProject task.
    developer_request: str | None
    openproject_task_description: str | None

    # Pipeline intermediate representations
    schema_snapshot: Schema | None
    project_ir: ProjectIR | None
    relational_model: RelationalModel | None

    # Parallel branches accumulate into these
    performance_recommendations: Annotated[
        list[PerformanceRecommendation], _merge_list
    ]
    security_recommendations: Annotated[
        list[SecurityRecommendation], _merge_list
    ]

    # Artifacts
    diagram: DiagramArtifact | None
    migration_plan: MigrationPlan | None
    sql_artifact: SqlArtifact | None
    openproject_update: OpenProjectTaskUpdate | None

    # Status / control
    status: AnalysisStatus
    approval_state: ApprovalState
    rejection_feedback: str | None
    errors: Annotated[list[str], _merge_errors]

    # Retake metadata. Set when the DBA reopens an already-completed
    # task via ``POST /analysis/retake`` so the OpenProject comment
    # header can flag this run as a new approach.
    is_retake: bool
    parent_session_id: str | None
