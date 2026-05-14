"""Database-level domain models (raw schema as introspected)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from backend.domain.enums import DatabaseType


class DatabaseConnection(BaseModel):
    """Customer database connection metadata.

    The password is held as ``SecretStr`` and is **never** serialized in
    logs, prompts, traces, or workflow state. Only the encrypted blob
    reference is propagated through the workflow.
    """

    model_config = ConfigDict(frozen=True)

    database_type: DatabaseType
    host: str
    port: int = Field(gt=0, lt=65536)
    database_name: str
    username: str
    password: SecretStr

    def safe_repr(self) -> str:
        """Human-readable string with the password redacted."""
        return (
            f"{self.database_type}://{self.username}:***"
            f"@{self.host}:{self.port}/{self.database_name}"
        )


class Column(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    data_type: str
    nullable: bool = True
    default: str | None = None
    is_primary_key: bool = False
    is_unique: bool = False
    comment: str | None = None


class ForeignKey(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str | None = None
    columns: list[str]
    referenced_table: str
    referenced_columns: list[str]
    on_delete: str | None = None
    on_update: str | None = None


class Index(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    columns: list[str]
    unique: bool = False
    index_type: str | None = None


class Constraint(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    constraint_type: str  # CHECK, UNIQUE, EXCLUSION, etc.
    expression: str | None = None
    columns: list[str] = Field(default_factory=list)


class Table(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    schema_name: str = "public"
    columns: list[Column]
    primary_key: list[str] = Field(default_factory=list)
    foreign_keys: list[ForeignKey] = Field(default_factory=list)
    indexes: list[Index] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    comment: str | None = None
    estimated_row_count: int | None = None
