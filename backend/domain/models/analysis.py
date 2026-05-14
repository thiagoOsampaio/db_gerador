"""Aggregate analysis session and result models."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

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


class AnalysisResult(BaseModel):
    """Final aggregated analysis output (no secrets)."""

    model_config = ConfigDict(frozen=True)

    schema_snapshot: Schema | None = None
    project_ir: ProjectIR | None = None
    relational_model: RelationalModel | None = None
    performance_recommendations: list[PerformanceRecommendation] = Field(default_factory=list)
    security_recommendations: list[SecurityRecommendation] = Field(default_factory=list)
    diagram: DiagramArtifact | None = None
    migration_plan: MigrationPlan | None = None
    sql_artifact: SqlArtifact | None = None
    openproject_update: OpenProjectTaskUpdate | None = None


class AnalysisSession(BaseModel):
    """Persisted analysis session metadata. Never carries raw credentials."""

    model_config = ConfigDict(frozen=False)

    session_id: UUID = Field(default_factory=uuid4)
    user_email: str
    openproject_task_id: str
    status: AnalysisStatus = AnalysisStatus.PENDING
    approval_state: ApprovalState = ApprovalState.PENDING
    rejection_feedback: str | None = None
    errors: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    result: AnalysisResult = Field(default_factory=AnalysisResult)
