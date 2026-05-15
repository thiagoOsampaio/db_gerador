"""HTTP request/response Pydantic models.

The customer database password lives ONLY in :class:`StartAnalysisRequest`
during the lifetime of one request. It is immediately encrypted via the
``CredentialVault`` and never returned to clients in any response.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr

from backend.domain.enums import AnalysisStatus, ApprovalState, DatabaseType
from backend.domain.models.artifacts import DiagramArtifact, SqlArtifact
from backend.domain.models.openproject import OpenProjectTaskUpdate
from backend.domain.models.recommendations import (
    PerformanceRecommendation,
    SecurityRecommendation,
)
from backend.domain.models.schema import Entity, Relationship, Schema


class StartAnalysisRequest(BaseModel):
    """Request body for ``POST /analysis/start``."""

    model_config = ConfigDict(extra="forbid")

    # Identity
    user_email: EmailStr
    openproject_task_id: str = Field(min_length=1, max_length=64)
    # User-supplied OpenProject API token. Encrypted on arrival and
    # never returned in any response.
    openproject_token: SecretStr

    # Free-form description of what the developer wants the analysis to
    # accomplish. Combined with the OpenProject task description to form
    # the authoritative requirement statement passed to the agents.
    developer_request: str = Field(min_length=1, max_length=8000)

    # Customer database connection (encrypted on arrival)
    database_type: DatabaseType
    database_host: str = Field(min_length=1)
    database_port: int = Field(gt=0, lt=65536)
    database_name: str = Field(min_length=1)
    database_username: str = Field(min_length=1)
    database_password: SecretStr

    # Optional metadata
    framework_name: str | None = None
    orm_name: str | None = None
    project_metadata: dict[str, Any] = Field(default_factory=dict)
    extracted_schema: Schema | None = None
    entities: list[Entity] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)


class StartAnalysisResponse(BaseModel):
    session_id: UUID
    status: AnalysisStatus
    approval_state: ApprovalState
    message: str = "Analysis started"


class StatusResponse(BaseModel):
    session_id: UUID
    status: AnalysisStatus
    approval_state: ApprovalState
    rejection_feedback: str | None = None
    errors: list[str] = Field(default_factory=list)
    updated_at: datetime


class AnalysisResponse(BaseModel):
    """Full state snapshot for ``GET /analysis/{id}``."""

    session_id: UUID
    user_email: EmailStr
    openproject_task_id: str
    status: AnalysisStatus
    approval_state: ApprovalState
    rejection_feedback: str | None = None
    errors: list[str] = Field(default_factory=list)
    diagram: DiagramArtifact | None = None
    sql_artifact: SqlArtifact | None = None
    performance_recommendations: list[PerformanceRecommendation] = Field(default_factory=list)
    security_recommendations: list[SecurityRecommendation] = Field(default_factory=list)
    openproject_update: OpenProjectTaskUpdate | None = None
    created_at: datetime
    updated_at: datetime


class DiagramResponse(BaseModel):
    session_id: UUID
    format: str = "mermaid"
    content: str
    summary: str | None = None


class SqlResponse(BaseModel):
    session_id: UUID
    dialect: str = "postgresql"
    ddl: str
    alembic_revision: str | None = None
    summary: str | None = None


class RejectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feedback: str | None = None
