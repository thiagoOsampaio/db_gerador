"""Performance Agent — indexing, partitioning, scalability recommendations."""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.agents.base import BaseAgent
from backend.agents.knowledge import build_system_prompt
from backend.domain.models.ir import RelationalModel
from backend.domain.models.recommendations import PerformanceRecommendation

_ROLE_PROMPT = """\
You are a senior database performance engineer.

Analyze the provided RelationalModel and produce concrete performance
recommendations.

Cover:
- indexing strategy (B-tree, partial, composite, covering)
- query optimization hints
- partitioning candidates (by range, list, or hash)
- scalability concerns (hot rows, write amplification, large tables)

Each recommendation must include:
- a precise title
- a category from: index | partitioning | query | scalability | maintenance
- a severity (info/low/medium/high/critical)
- affected tables/columns
- optional suggested SQL
- a rationale explaining the recommendation

DO NOT include credentials or any secret data.
Reply strictly using the provided structured schema.
"""

_SYSTEM_PROMPT = build_system_prompt(_ROLE_PROMPT)


class PerformanceOutput(BaseModel):
    recommendations: list[PerformanceRecommendation] = Field(default_factory=list)


class PerformanceAgent(BaseAgent[RelationalModel, PerformanceOutput]):
    name = "performance"
    output_schema = PerformanceOutput

    def build_system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    def build_user_prompt(self, payload: RelationalModel) -> str:
        return (
            "RelationalModel (JSON):\n"
            f"{payload.model_dump_json(indent=2)}\n\n"
            "Return performance recommendations."
        )
