"""Strongly-typed Pydantic v2 domain models.

All cross-layer communication (API ↔ workflow ↔ agents ↔ services) uses
these models. Free-form strings are never used as the primary data format.
"""

from backend.domain.models.analysis import (
    AnalysisResult,
    AnalysisSession,
)
from backend.domain.models.artifacts import (
    DiagramArtifact,
    MigrationPlan,
    MigrationStep,
    SqlArtifact,
)
from backend.domain.models.database import (
    Column,
    Constraint,
    DatabaseConnection,
    ForeignKey,
    Index,
    Table,
)
from backend.domain.models.ir import (
    DomainEntity,
    DomainModel,
    InferredAttribute,
    ProjectIR,
    RelationalAttribute,
    RelationalModel,
    RelationalRelationship,
    RelationalTable,
)
from backend.domain.models.openproject import (
    OpenProjectTaskUpdate,
    TaskAttachment,
    TaskComment,
)
from backend.domain.models.recommendations import (
    PerformanceRecommendation,
    SecurityRecommendation,
)
from backend.domain.models.schema import (
    Entity,
    Relationship,
    Schema,
)

__all__ = [
    "AnalysisResult",
    "AnalysisSession",
    "Column",
    "Constraint",
    "DatabaseConnection",
    "DiagramArtifact",
    "DomainEntity",
    "DomainModel",
    "Entity",
    "ForeignKey",
    "Index",
    "InferredAttribute",
    "MigrationPlan",
    "MigrationStep",
    "OpenProjectTaskUpdate",
    "PerformanceRecommendation",
    "ProjectIR",
    "RelationalAttribute",
    "RelationalModel",
    "RelationalRelationship",
    "RelationalTable",
    "Relationship",
    "Schema",
    "SecurityRecommendation",
    "SqlArtifact",
    "Table",
    "TaskAttachment",
    "TaskComment",
]
