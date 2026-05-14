"""Deterministic Mermaid ER diagram renderer.

Receives a fully-typed ``RelationalModel`` and produces a Mermaid
``erDiagram`` block. Pure function — no LLM, no I/O.
"""

from __future__ import annotations

import re

from backend.domain.enums import Cardinality
from backend.domain.exceptions import DiagramGenerationError
from backend.domain.models.artifacts import DiagramArtifact
from backend.domain.models.ir import RelationalModel, RelationalTable

# Mermaid cardinality syntax: <left>--<right>
#   |o   zero or one
#   ||   exactly one
#   o{   zero or many
#   o|   exactly zero or one (rare)
#   }o   many to one (zero or many)
_CARDINALITY_NOTATION: dict[Cardinality, tuple[str, str]] = {
    Cardinality.ONE_TO_ONE: ("||--||", "has"),
    Cardinality.ONE_TO_MANY: ("||--o{", "has"),
    Cardinality.MANY_TO_ONE: ("}o--||", "belongs_to"),
    Cardinality.MANY_TO_MANY: ("}o--o{", "associates"),
}

_IDENT = re.compile(r"[^A-Z0-9_]")


def _normalize_entity_name(name: str) -> str:
    """Mermaid identifiers must be uppercase letters/digits/underscores."""
    return _IDENT.sub("_", name.upper())


class MermaidRenderer:
    """Render a ``RelationalModel`` to a Mermaid ER diagram string."""

    def render(self, model: RelationalModel) -> DiagramArtifact:
        if not model.tables:
            raise DiagramGenerationError("Cannot render an empty relational model")

        lines: list[str] = ["erDiagram"]
        for table in model.tables:
            lines.extend(self._render_table(table))

        for rel in model.relationships:
            notation, default_label = _CARDINALITY_NOTATION[rel.cardinality]
            label = rel.name or default_label
            lines.append(
                f"    {_normalize_entity_name(rel.source_table)} {notation} "
                f"{_normalize_entity_name(rel.target_table)} : {label}"
            )

        content = "\n".join(lines)
        return DiagramArtifact(
            content=content,
            summary=f"{len(model.tables)} tables, {len(model.relationships)} relationships",
        )

    @staticmethod
    def _render_table(table: RelationalTable) -> list[str]:
        entity = _normalize_entity_name(table.name)
        body: list[str] = [f"    {entity} {{"]
        for attr in table.attributes:
            sql_type = _normalize_entity_name(attr.sql_type.split("(")[0])
            markers: list[str] = []
            if attr.is_primary_key or attr.name in table.primary_key:
                markers.append("PK")
            if attr.is_unique:
                markers.append("UK")
            marker_str = f" {','.join(markers)}" if markers else ""
            body.append(f"        {sql_type} {attr.name}{marker_str}")
        body.append("    }")
        return body
