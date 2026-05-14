"""Performance and security recommendations produced by specialized agents."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from backend.domain.enums import Severity


class PerformanceRecommendation(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    category: str  # "index" | "partitioning" | "query" | "scalability" ...
    severity: Severity = Severity.MEDIUM
    description: str
    affected_tables: list[str] = Field(default_factory=list)
    affected_columns: list[str] = Field(default_factory=list)
    suggested_sql: str | None = None
    rationale: str | None = None


class SecurityRecommendation(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    category: str  # "encryption" | "rls" | "audit" | "pii" | "lgpd" ...
    severity: Severity = Severity.MEDIUM
    description: str
    affected_tables: list[str] = Field(default_factory=list)
    affected_columns: list[str] = Field(default_factory=list)
    compliance_tags: list[str] = Field(default_factory=list)  # "LGPD", "GDPR"
    suggested_action: str | None = None
    rationale: str | None = None
