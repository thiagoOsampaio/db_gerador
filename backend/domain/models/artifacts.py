"""Generated artifacts: diagrams, SQL, migration plans."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class DiagramArtifact(BaseModel):
    """Mermaid ER diagram artifact."""

    model_config = ConfigDict(frozen=True)

    format: str = "mermaid"
    content: str
    generated_at: datetime = Field(default_factory=_utcnow)
    summary: str | None = None


class MigrationStep(BaseModel):
    model_config = ConfigDict(frozen=True)

    order: int
    operation: str  # "create_table" | "add_column" | "create_index" | ...
    target: str
    sql: str
    description: str | None = None


class MigrationPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    steps: list[MigrationStep] = Field(default_factory=list)
    dialect: str = "postgresql"
    summary: str | None = None


class SqlArtifact(BaseModel):
    """Final SQL DDL artifact (PostgreSQL by default)."""

    model_config = ConfigDict(frozen=True)

    dialect: str = "postgresql"
    ddl: str
    alembic_revision: str | None = None
    generated_at: datetime = Field(default_factory=_utcnow)
    summary: str | None = None
