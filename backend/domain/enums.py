"""Domain-wide enumerations."""

from __future__ import annotations

from enum import StrEnum


class DatabaseType(StrEnum):
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SQLSERVER = "sqlserver"


class AnalysisStatus(StrEnum):
    """Lifecycle states for an analysis session."""

    PENDING = "pending"
    VALIDATING = "validating"
    INTROSPECTING = "introspecting"
    ANALYZING_PROJECT = "analyzing_project"
    MODELING = "modeling"
    ANALYZING_PERFORMANCE = "analyzing_performance"
    ANALYZING_SECURITY = "analyzing_security"
    MERGING = "merging"
    GENERATING_ERD = "generating_erd"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    GENERATING_SQL = "generating_sql"
    UPDATING_OPENPROJECT = "updating_openproject"
    COMPLETED = "completed"
    FAILED = "failed"


class ArtifactType(StrEnum):
    DIAGRAM_MERMAID = "diagram_mermaid"
    SQL_DDL = "sql_ddl"
    ALEMBIC_MIGRATION = "alembic_migration"
    ANALYSIS_REPORT = "analysis_report"


class Cardinality(StrEnum):
    ONE_TO_ONE = "one_to_one"
    ONE_TO_MANY = "one_to_many"
    MANY_TO_ONE = "many_to_one"
    MANY_TO_MANY = "many_to_many"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ApprovalState(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
