"""SQL generator produces valid-looking PostgreSQL DDL deterministically."""

from __future__ import annotations

import pytest

from backend.domain.enums import Cardinality
from backend.domain.exceptions import SqlGenerationError
from backend.domain.models.ir import (
    RelationalAttribute,
    RelationalIndex,
    RelationalModel,
    RelationalRelationship,
    RelationalTable,
)
from backend.services.rendering.sql_generator import SqlGenerator


def _model() -> RelationalModel:
    return RelationalModel(
        tables=[
            RelationalTable(
                name="users",
                description="Customer accounts",
                attributes=[
                    RelationalAttribute(
                        name="id",
                        sql_type="UUID",
                        nullable=False,
                        is_primary_key=True,
                    ),
                    RelationalAttribute(
                        name="email",
                        sql_type="VARCHAR(255)",
                        nullable=False,
                        is_unique=True,
                    ),
                ],
                primary_key=["id"],
                indexes=[
                    RelationalIndex(name="ix_users_email", columns=["email"], unique=True),
                ],
            ),
            RelationalTable(
                name="orders",
                attributes=[
                    RelationalAttribute(
                        name="id",
                        sql_type="UUID",
                        nullable=False,
                        is_primary_key=True,
                    ),
                    RelationalAttribute(
                        name="user_id", sql_type="UUID", nullable=False
                    ),
                ],
                primary_key=["id"],
            ),
        ],
        relationships=[
            RelationalRelationship(
                name="fk_orders_users",
                source_table="orders",
                source_columns=["user_id"],
                target_table="users",
                target_columns=["id"],
                cardinality=Cardinality.MANY_TO_ONE,
            )
        ],
    )


def test_generate_emits_tables_indexes_and_foreign_keys() -> None:
    artifact, plan = SqlGenerator().generate(_model())
    ddl = artifact.ddl
    assert 'CREATE TABLE "users"' in ddl
    assert 'PRIMARY KEY ("id")' in ddl
    assert 'CREATE UNIQUE INDEX "ix_users_email"' in ddl
    assert 'ALTER TABLE "orders"' in ddl
    assert 'FOREIGN KEY ("user_id") REFERENCES "users" ("id")' in ddl
    assert 'COMMENT ON TABLE "users" IS' in ddl
    assert len(plan.steps) == 4  # 2 tables + 1 index + 1 fk


def test_alembic_emitter() -> None:
    artifact, _ = SqlGenerator().generate(_model(), emit_alembic=True)
    assert artifact.alembic_revision is not None
    assert "def upgrade" in artifact.alembic_revision
    assert "def downgrade" in artifact.alembic_revision


def test_empty_model_raises() -> None:
    with pytest.raises(SqlGenerationError):
        SqlGenerator().generate(RelationalModel(tables=[]))
