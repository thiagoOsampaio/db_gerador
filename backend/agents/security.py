"""Security Agent — sensitive data, encryption, RLS, LGPD/GDPR."""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.agents.base import BaseAgent
from backend.agents.knowledge import build_system_prompt
from backend.agents.project_analysis import _compact_schema
from backend.domain.models.ir import RelationalModel
from backend.domain.models.recommendations import SecurityRecommendation
from backend.domain.models.schema import Schema


class SecurityAgentInput(BaseModel):
    relational_model: RelationalModel
    schema_snapshot: Schema | None = None


class SecurityOutput(BaseModel):
    recommendations: list[SecurityRecommendation] = Field(default_factory=list)


_ROLE_PROMPT = """\
You are a senior security and data-privacy engineer.

Analyze the provided RelationalModel (and optional source schema) for
security concerns and produce concrete recommendations.

Cover:
- sensitive / PII / PHI data identification
- encryption at rest and in transit
- row-level security (RLS) and multi-tenant isolation
- auditability (created_at/updated_at, audit tables, change capture)
- LGPD and GDPR compliance (data subject rights, retention, consent)
- least-privilege access patterns

Each recommendation must include:
- a precise title
- a category from: encryption | rls | audit | pii | lgpd | gdpr | access | tenancy
- a severity (info/low/medium/high/critical)
- affected tables/columns
- compliance_tags (e.g., ["LGPD"], ["GDPR"])
- a suggested action and rationale

DO NOT include credentials or any secret data.
Reply strictly using the provided structured schema.
"""

_SYSTEM_PROMPT = build_system_prompt(_ROLE_PROMPT)


class SecurityAgent(BaseAgent[SecurityAgentInput, SecurityOutput]):
    name = "security"
    output_schema = SecurityOutput

    def build_system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    def build_user_prompt(self, payload: SecurityAgentInput) -> str:
        snapshot = _compact_schema(payload.schema_snapshot)
        return (
            "RelationalModel (JSON):\n"
            f"{payload.relational_model.model_dump_json(indent=2)}\n\n"
            "Source schema snapshot (compact, optional):\n"
            f"{snapshot}\n\n"
            "Return security recommendations."
        )
