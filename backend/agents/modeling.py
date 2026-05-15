"""Modeling Agent — converts ``ProjectIR`` into a normalized ``RelationalModel``."""

from __future__ import annotations

from pydantic import BaseModel

from backend.agents.base import BaseAgent
from backend.domain.models.ir import ProjectIR, RelationalModel

_SYSTEM_PROMPT = """\
You are a senior relational database designer.

Convert the provided Project IR into a normalized relational model
targeting PostgreSQL by default.

SCOPE — CRITICAL:
- The IR has already been scoped to the developer's request. The
  resulting RelationalModel MUST include ONLY tables that map back to
  entities present in the IR. DO NOT reintroduce tables from the wider
  database that were intentionally left out of the IR.
- ``relationships`` MUST only connect tables present in ``tables``.

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
- ``RelationalTable.description`` MUST explain the purpose of that table
  in the requested change: whether it is being created, altered, or
  included as a foreign-key reference, and the rationale behind its
  shape (chosen keys, notable columns, denormalization, etc.).
- ``RelationalModel.notes`` MUST be a concise narrative explaining the
  overall modeling decisions: normalization choices, trade-offs, why
  the proposed shape satisfies the request. This narrative will be
  surfaced to the requester.
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
