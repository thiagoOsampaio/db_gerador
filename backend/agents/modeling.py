"""Modeling Agent — converts ``ProjectIR`` into a normalized ``RelationalModel``."""

from __future__ import annotations

from pydantic import BaseModel

from backend.agents.base import BaseAgent
from backend.domain.models.ir import ProjectIR, RelationalModel

_SYSTEM_PROMPT = """\
You are a senior relational database designer.

Convert the provided Project IR into a normalized relational model
targeting PostgreSQL by default.

Requirements:
- Normalize to at least 3NF unless explicit denormalization is justified.
- Use snake_case for table and column names.
- Every table must have a primary key. Prefer UUID v4 (sql_type "UUID")
  unless a natural key is clearly better.
- Foreign key constraints use ON DELETE RESTRICT and ON UPDATE CASCADE
  by default.
- Suggest indexes on all foreign-key columns and on columns commonly used
  for filtering or sorting.
- Use precise SQL types (e.g., VARCHAR(255), TIMESTAMPTZ, NUMERIC(10,2)).
- DO NOT include credentials, hostnames, or any secret data.
- Reply strictly using the provided structured schema.
"""


class ModelingAgent(BaseAgent[ProjectIR, RelationalModel]):
    name = "modeling"
    output_schema = RelationalModel

    def build_system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    def build_user_prompt(self, payload: ProjectIR) -> str:
        return (
            "Project IR (JSON):\n"
            f"{payload.model_dump_json(indent=2)}\n\n"
            "Produce a normalized RelationalModel."
        )


# Convenience alias for typed inputs in workflow code.
ModelingInput = ProjectIR
ModelingOutput = RelationalModel


# Re-export for star-import friendliness
class _Marker(BaseModel):  # pragma: no cover
    """Anchor for IDE auto-completion."""
