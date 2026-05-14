"""Async engine factory for customer databases.

Engines created here are *short-lived*: built only for the introspection
step of the workflow and disposed immediately afterwards. The plaintext
``DatabaseConnection`` object never escapes this module's scope.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from urllib.parse import quote_plus

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from backend.domain.enums import DatabaseType
from backend.domain.exceptions import DatabaseConnectionError
from backend.domain.models.database import DatabaseConnection

_DRIVERS: dict[DatabaseType, str] = {
    DatabaseType.POSTGRESQL: "postgresql+asyncpg",
    DatabaseType.MYSQL: "mysql+aiomysql",
    DatabaseType.SQLSERVER: "mssql+aioodbc",
}


def _build_dsn(connection: DatabaseConnection) -> str:
    driver = _DRIVERS.get(connection.database_type)
    if driver is None:
        raise DatabaseConnectionError(
            f"Unsupported database type: {connection.database_type}"
        )
    user = quote_plus(connection.username)
    pwd = quote_plus(connection.password.get_secret_value())
    host = connection.host
    port = connection.port
    db = connection.database_name
    return f"{driver}://{user}:{pwd}@{host}:{port}/{db}"


class DatabaseConnector:
    """Factory for ephemeral customer-database engines."""

    @asynccontextmanager
    async def engine(self, connection: DatabaseConnection) -> AsyncIterator[AsyncEngine]:
        """Yield a *read-only* ``AsyncEngine`` that is disposed on exit.

        The engine is configured with ``default_transaction_read_only``
        on PostgreSQL so any attempt to issue DDL/DML against the
        customer database raises immediately. The application contract
        is read-only: we introspect, never apply changes.
        """
        dsn = _build_dsn(connection)
        connect_args: dict = {}
        if connection.database_type == DatabaseType.POSTGRESQL:
            connect_args["server_settings"] = {
                "default_transaction_read_only": "on",
            }
        engine = create_async_engine(
            dsn,
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=0,
            connect_args=connect_args,
        )
        try:
            yield engine
        finally:
            await engine.dispose()
