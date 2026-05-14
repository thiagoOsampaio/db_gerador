"""Mermaid renderer determinism + structural correctness."""

from __future__ import annotations

import pytest

from backend.domain.enums import Cardinality
from backend.domain.exceptions import DiagramGenerationError
from backend.domain.models.ir import (
    RelationalAttribute,
    RelationalModel,
    RelationalRelationship,
    RelationalTable,
)
from backend.services.rendering.mermaid import MermaidRenderer


def _sample_model() -> RelationalModel:
    users = RelationalTable(
        name="users",
        attributes=[
            RelationalAttribute(name="id", sql_type="UUID", nullable=False, is_primary_key=True),
            RelationalAttribute(name="email", sql_type="VARCHAR(255)", nullable=False, is_unique=True),
        ],
        primary_key=["id"],
    )
    orders = RelationalTable(
        name="orders",
        attributes=[
            RelationalAttribute(name="id", sql_type="UUID", nullable=False, is_primary_key=True),
            RelationalAttribute(name="user_id", sql_type="UUID", nullable=False),
        ],
        primary_key=["id"],
    )
    rel = RelationalRelationship(
        name="orders_user_fk",
        source_table="orders",
        source_columns=["user_id"],
        target_table="users",
        target_columns=["id"],
        cardinality=Cardinality.MANY_TO_ONE,
    )
    return RelationalModel(tables=[users, orders], relationships=[rel])


def test_renders_entities_and_relationship() -> None:
    out = MermaidRenderer().render(_sample_model())
    assert out.content.startswith("erDiagram")
    assert "USERS {" in out.content
    assert "ORDERS {" in out.content
    assert "UUID id PK" in out.content
    assert "VARCHAR email UK" in out.content
    assert "ORDERS }o--|| USERS" in out.content


def test_empty_model_raises() -> None:
    with pytest.raises(DiagramGenerationError):
        MermaidRenderer().render(RelationalModel(tables=[]))


def test_renderer_is_deterministic() -> None:
    model = _sample_model()
    r = MermaidRenderer()
    assert r.render(model).content == r.render(model).content
