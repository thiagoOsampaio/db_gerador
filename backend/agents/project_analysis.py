"""Project Analysis Agent — produces a ``ProjectIR`` from raw inputs."""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.agents.base import BaseAgent
from backend.domain.models.ir import ProjectIR
from backend.domain.models.schema import Schema

_SYSTEM_PROMPT = """\
You are a senior database architect.

Your task is to analyze the provided project metadata, database schema
and the developer's stated requirements, then produce a
framework-agnostic Project Intermediate Representation (IR).

Guidelines:
- Treat the developer request and the OpenProject task description as
  the authoritative statement of intent. The IR must satisfy them.
- Infer the framework and ORM if hinted at, otherwise leave them null.
- Each entity must have a clear name and inferred attributes.
- Relationships use explicit cardinality (one_to_one / one_to_many /
  many_to_one / many_to_many).
- Detect ORM patterns (e.g., polymorphic, single-table-inheritance, audit
  columns) and list them under detected_patterns.
- If the user has rejected a previous iteration and provided feedback,
  treat that feedback as authoritative and adjust the IR accordingly.
- DO NOT hallucinate entities not justified by the input.
- DO NOT include credentials, hostnames, ports, or any secret data.
- Reply strictly using the provided structured schema.
"""


class ProjectAnalysisInput(BaseModel):
    framework_name: str | None = None
    orm_name: str | None = None
    project_metadata: dict[str, object] = Field(default_factory=dict)
    schema_snapshot: Schema | None = None
    user_entities: list[str] = Field(default_factory=list)
    user_relationships: list[str] = Field(default_factory=list)
    # Authoritative natural-language requirements that drive the IR.
    developer_request: str | None = None
    openproject_task_description: str | None = None
    # Populated only when re-entering the workflow after a rejection.
    rejection_feedback: str | None = None


def _compact_schema(schema: Schema | None) -> str:
    """Render a Schema as a short, line-oriented text block.

    Sending the full ``model_dump_json`` of a 37-table schema to Gemini
    costs hundreds of thousands of tokens and minutes of latency. This
    compact form keeps every fact the LLM needs (columns, types,
    primary/foreign keys, indexes) with a fraction of the token cost.
    """
    if not schema:
        return "null"
    lines: list[str] = []
    for t in schema.tables:
        lines.append(f"Table: {t.name}")
        for c in t.columns:
            tags: list[str] = []
            if c.is_primary_key:
                tags.append("PK")
            if c.is_unique:
                tags.append("UNIQUE")
            if not c.nullable:
                tags.append("NOT NULL")
            tag_str = (" [" + ", ".join(tags) + "]") if tags else ""
            lines.append(f"  - {c.name} {c.data_type}{tag_str}")
        if t.foreign_keys:
            lines.append("  Foreign keys:")
            for fk in t.foreign_keys:
                lines.append(
                    f"    - ({', '.join(fk.columns)}) -> "
                    f"{fk.referenced_table}({', '.join(fk.referenced_columns)})"
                )
        if t.indexes:
            lines.append("  Indexes:")
            for idx in t.indexes:
                uniq = " UNIQUE" if idx.unique else ""
                lines.append(f"    - {idx.name}{uniq} ({', '.join(idx.columns)})")
        lines.append("")
    return "\n".join(lines)


class ProjectAnalysisAgent(BaseAgent[ProjectAnalysisInput, ProjectIR]):
    name = "project_analysis"
    output_schema = ProjectIR

    def build_system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    def build_user_prompt(self, payload: ProjectAnalysisInput) -> str:
        schema_text = _compact_schema(payload.schema_snapshot)
        feedback_block = (
            f"\nUser rejected the previous iteration with this feedback "
            f"(must be addressed):\n{payload.rejection_feedback}\n"
            if payload.rejection_feedback
            else ""
        )
        return (
            f"Developer request:\n{payload.developer_request or '(none provided)'}\n\n"
            f"OpenProject task description:\n"
            f"{payload.openproject_task_description or '(not available)'}\n\n"
            f"Framework hint: {payload.framework_name or 'unknown'}\n"
            f"ORM hint: {payload.orm_name or 'unknown'}\n"
            f"User-provided entities: {payload.user_entities}\n"
            f"User-provided relationships: {payload.user_relationships}\n"
            f"Project metadata: {payload.project_metadata}\n"
            f"Introspected schema:\n{schema_text}\n"
            f"{feedback_block}"
        )
