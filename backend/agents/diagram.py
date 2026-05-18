

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from backend.agents.base import BaseAgent
from backend.agents.knowledge import build_system_prompt
from backend.domain.models.artifacts import DiagramArtifact
from backend.domain.models.ir import ProjectIR, RelationalModel
from backend.services.llm.gemini import GeminiService
from backend.services.rendering.mermaid import MermaidRenderer


class DiagramAgentInput(BaseModel):
    """Input bundle for the DiagramAgent."""

    model_config = ConfigDict(frozen=True)

    developer_request: str | None = None
    openproject_task_description: str | None = None
    project_ir: ProjectIR | None = None
    relational_model: RelationalModel


_ROLE_PROMPT = """\
You are a senior technical architect explaining a database solution
visually to a development team.

Your task is to produce a Mermaid.js diagram that VISUALLY EXPLAINS HOW
THE PROPOSED SOLUTION ADDRESSES THE DEVELOPER'S REQUEST. The diagram is
a communication tool aimed at the requester - NOT a complete dump of
the database schema.

Guidelines:
- Choose the Mermaid diagram type that best communicates the solution:
    * ``erDiagram`` when the answer is mainly about new/changed tables
      and their relationships;
    * ``flowchart`` (LR or TD) when the answer is mainly about how data
      flows between entities, processes, or modules;
    * ``sequenceDiagram`` when the answer is a process/interaction
      between actors over time.
- INCLUDE ONLY the entities/tables that are directly relevant to the
  solution (those created, altered, or referenced as foreign keys).
  DO NOT list every table from the introspected database.
- Highlight which elements are NEW vs ALTERED vs REFERENCED. Use node
  labels, comments, or grouping (subgraphs) when the diagram type
  supports it.
  IMPORTANT: ``erDiagram`` DOES NOT support ``subgraph``, ``classDef``, or ``class``.
  If you must use subgraphs or styling, choose a ``flowchart`` instead, or simply
  add notes to the ``erDiagram`` without using invalid syntax.
- Keep the diagram small enough to be read at a glance - prefer clarity
  over completeness.
- The ``content`` field MUST contain ONLY valid Mermaid source code.
  It MUST start with the diagram type keyword (``erDiagram``,
  ``flowchart``, ``sequenceDiagram``, ...). DO NOT wrap it in markdown
  code fences (no ```mermaid).
- The ``format`` field MUST be the string ``"mermaid"``.
- The ``summary`` field MUST be a brief explanation (1-3 sentences)
  describing what the diagram shows and how it solves the request.
- DO NOT include credentials, hostnames, ports, or any secret data.
- Reply strictly using the provided structured schema.
"""

_SYSTEM_PROMPT = build_system_prompt(_ROLE_PROMPT)


class DiagramAgent(BaseAgent[DiagramAgentInput, DiagramArtifact]):
    name = "diagram"
    output_schema = DiagramArtifact

    def __init__(
        self,
        llm: GeminiService,
        renderer: MermaidRenderer | None = None,
    ) -> None:
        super().__init__(llm)
        # ``renderer`` is kept for backwards compatibility with the DI
        # wiring in ``backend/main.py``; it is no longer used because
        # the diagram is now produced by the LLM.
        self._renderer = renderer

    def build_system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    def build_user_prompt(self, payload: DiagramAgentInput) -> str:
        lines: list[str] = []

        lines.append("Developer request:")
        lines.append(payload.developer_request or "(none provided)")
        lines.append("")

        if payload.openproject_task_description:
            lines.append("OpenProject task description:")
            lines.append(payload.openproject_task_description)
            lines.append("")

        if payload.project_ir is not None:
            lines.append("Project IR (scoped to the request):")
            lines.append(payload.project_ir.model_dump_json(indent=2))
            lines.append("")

        lines.append("Relational model (proposed solution):")
        for table in payload.relational_model.tables:
            desc = f" - {table.description}" if table.description else ""
            lines.append(f"- Table `{table.name}`{desc}")
            for attr in table.attributes:
                tags: list[str] = []
                if attr.is_primary_key:
                    tags.append("PK")
                if attr.is_unique:
                    tags.append("UNIQUE")
                if not attr.nullable:
                    tags.append("NOT NULL")
                tag_str = (" [" + ", ".join(tags) + "]") if tags else ""
                lines.append(f"    * {attr.name} {attr.sql_type}{tag_str}")
        if payload.relational_model.relationships:
            lines.append("")
            lines.append("Relationships:")
            for rel in payload.relational_model.relationships:
                lines.append(
                    f"- {rel.source_table}({', '.join(rel.source_columns)}) "
                    f"--{rel.cardinality.value}--> "
                    f"{rel.target_table}({', '.join(rel.target_columns)})"
                )
        if payload.relational_model.notes:
            lines.append("")
            lines.append("Modeling notes:")
            lines.append(payload.relational_model.notes)

        lines.append("")
        lines.append(
            "Produce a Mermaid diagram that visually explains how this "
            "model solves the developer's request, plus a short summary "
            "in Brazilian Portuguese."
        )
        return "\n".join(lines)
