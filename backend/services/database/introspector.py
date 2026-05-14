"""Schema introspection over an async customer database engine."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from backend.domain.exceptions import SchemaIntrospectionError
from backend.domain.models.database import (
    Column,
    Constraint,
    ForeignKey,
    Index,
    Table,
)
from backend.domain.models.database import DatabaseConnection
from backend.domain.models.schema import Schema
from backend.observability.logging import get_logger
from backend.services.database.connector import DatabaseConnector

_logger = get_logger(__name__)


class DatabaseIntrospector:
    """Extract a structural ``Schema`` from a customer database.

    The introspector receives a ``DatabaseConnection`` once, opens a
    short-lived engine through ``DatabaseConnector``, and returns the
    sanitized ``Schema`` Pydantic model. Plaintext credentials are not
    retained anywhere after this method returns.
    """

    def __init__(self, connector: DatabaseConnector) -> None:
        self._connector = connector

    async def introspect(self, connection: DatabaseConnection) -> Schema:
        # Log only the dialect; host/user/db are sensitive metadata even
        # when the password is masked.
        _logger.info(
            "database.introspect.start",
            database_type=connection.database_type.value,
        )
        try:
            async with self._connector.engine(connection) as engine:
                tables = await self._collect_tables(engine)
        except SQLAlchemyError as exc:
            # Sanitize: SQLAlchemy errors sometimes embed the DSN.
            raise SchemaIntrospectionError(
                f"Failed to introspect schema: {type(exc).__name__}"
            ) from None

        schema = Schema(
            database_type=connection.database_type,
            database_name=connection.database_name,
            tables=tables,
            extracted_at=datetime.now(tz=timezone.utc).isoformat(),
        )
        _logger.info(
            "database.introspect.done",
            database_type=connection.database_type.value,
            table_count=len(tables),
        )
        return schema

    # ------------------------------------------------------------------
    # Internal helpers (run sync inspect inside run_sync)
    # ------------------------------------------------------------------
    async def _collect_tables(self, engine: AsyncEngine) -> list[Table]:
        async with engine.connect() as conn:
            return await conn.run_sync(self._inspect_sync)

    @staticmethod
    def _inspect_sync(conn: Connection) -> list[Table]:
        inspector = sa_inspect(conn)
        tables: list[Table] = []
        for table_name in inspector.get_table_names():
            cols = inspector.get_columns(table_name)
            pk = inspector.get_pk_constraint(table_name)
            fks = inspector.get_foreign_keys(table_name)
            idx = inspector.get_indexes(table_name)

            try:
                check_constraints = inspector.get_check_constraints(table_name)
            except NotImplementedError:
                check_constraints = []
            try:
                unique_constraints = inspector.get_unique_constraints(table_name)
            except NotImplementedError:
                unique_constraints = []

            columns = [
                Column(
                    name=c["name"],
                    data_type=str(c["type"]),
                    nullable=bool(c.get("nullable", True)),
                    default=str(c["default"]) if c.get("default") is not None else None,
                    is_primary_key=c["name"] in (pk.get("constrained_columns") or []),
                    is_unique=False,  # set below from unique_constraints
                    comment=c.get("comment"),
                )
                for c in cols
            ]

            unique_cols = {
                col
                for uc in unique_constraints
                for col in (uc.get("column_names") or [])
                if len(uc.get("column_names") or []) == 1
            }
            columns = [
                col.model_copy(update={"is_unique": True}) if col.name in unique_cols else col
                for col in columns
            ]

            tables.append(
                Table(
                    name=table_name,
                    columns=columns,
                    primary_key=list(pk.get("constrained_columns") or []),
                    foreign_keys=[_fk_from_dict(fk) for fk in fks],
                    indexes=[_index_from_dict(i) for i in idx],
                    constraints=[
                        Constraint(
                            name=cc.get("name") or f"{table_name}_check",
                            constraint_type="CHECK",
                            expression=cc.get("sqltext"),
                        )
                        for cc in check_constraints
                    ]
                    + [
                        Constraint(
                            name=uc.get("name") or f"{table_name}_unique",
                            constraint_type="UNIQUE",
                            columns=list(uc.get("column_names") or []),
                        )
                        for uc in unique_constraints
                    ],
                )
            )
        return tables


def _fk_from_dict(fk: dict[str, Any]) -> ForeignKey:
    return ForeignKey(
        name=fk.get("name"),
        columns=list(fk.get("constrained_columns") or []),
        referenced_table=fk.get("referred_table") or "",
        referenced_columns=list(fk.get("referred_columns") or []),
        on_delete=(fk.get("options") or {}).get("ondelete"),
        on_update=(fk.get("options") or {}).get("onupdate"),
    )


def _index_from_dict(idx: dict[str, Any]) -> Index:
    return Index(
        name=idx.get("name") or "",
        columns=list(idx.get("column_names") or []),
        unique=bool(idx.get("unique", False)),
    )
