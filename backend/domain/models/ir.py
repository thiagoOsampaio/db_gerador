"""Intermediate Representations used between pipeline stages.

The pipeline is a deterministic compiler:
    Schema → ProjectIR → DomainModel → RelationalModel → ERD/SQL
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from backend.domain.enums import Cardinality


# ---------------------------------------------------------------------------
# Project IR — output of the ProjectAnalysisAgent
# ---------------------------------------------------------------------------
class InferredAttribute(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    inferred_type: str
    nullable: bool = True
    description: str | None = None


class InferredEntity(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    description: str | None = None
    source: str = "schema"  # "schema" | "orm" | "metadata"
    attributes: list[InferredAttribute] = Field(default_factory=list)


class InferredRelationship(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_entity: str
    target_entity: str
    cardinality: Cardinality
    rationale: str | None = None


class ProjectIR(BaseModel):
    """Framework-agnostic representation produced by ProjectAnalysisAgent."""

    model_config = ConfigDict(frozen=True)

    framework: str | None = None
    orm: str | None = None
    entities: list[InferredEntity] = Field(default_factory=list)
    relationships: list[InferredRelationship] = Field(default_factory=list)
    detected_patterns: list[str] = Field(default_factory=list)
    notes: str | None = None


# ---------------------------------------------------------------------------
# Domain Model — semantic abstraction
# ---------------------------------------------------------------------------
class DomainEntity(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    description: str | None = None
    business_keys: list[str] = Field(default_factory=list)


class DomainModel(BaseModel):
    model_config = ConfigDict(frozen=True)

    entities: list[DomainEntity] = Field(default_factory=list)
    relationships: list[InferredRelationship] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Relational Model — direct mapping to SQL
# ---------------------------------------------------------------------------
class RelationalAttribute(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    sql_type: str
    nullable: bool = True
    default: str | None = None
    is_primary_key: bool = False
    is_unique: bool = False
    description: str | None = None


class RelationalIndex(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    columns: list[str]
    unique: bool = False
    rationale: str | None = None


class RelationalTable(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    attributes: list[RelationalAttribute]
    primary_key: list[str] = Field(default_factory=list)
    indexes: list[RelationalIndex] = Field(default_factory=list)
    description: str | None = None


class RelationalRelationship(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    source_table: str
    source_columns: list[str]
    target_table: str
    target_columns: list[str]
    cardinality: Cardinality
    on_delete: str | None = "RESTRICT"
    on_update: str | None = "CASCADE"


class RelationalModel(BaseModel):
    """Normalized relational schema ready for SQL/ERD generation."""

    model_config = ConfigDict(frozen=True)

    tables: list[RelationalTable]
    relationships: list[RelationalRelationship] = Field(default_factory=list)
    naming_conventions: dict[str, str] = Field(default_factory=dict)
    notes: str | None = None
