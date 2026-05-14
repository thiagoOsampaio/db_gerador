"""High-level schema and entity domain models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from backend.domain.enums import Cardinality, DatabaseType
from backend.domain.models.database import Table


class Schema(BaseModel):
    """Introspected database schema (raw, structural)."""

    model_config = ConfigDict(frozen=True)

    database_type: DatabaseType
    database_name: str
    tables: list[Table] = Field(default_factory=list)
    extracted_at: str | None = None  # ISO timestamp


class Entity(BaseModel):
    """High-level business entity (post-analysis)."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str | None = None
    table_name: str | None = None
    attributes: list[str] = Field(default_factory=list)


class Relationship(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_entity: str
    target_entity: str
    cardinality: Cardinality
    description: str | None = None
