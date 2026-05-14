"""PostgreSQL-backed LangGraph checkpointer.

Uses the official ``langgraph-checkpoint-postgres`` package. The same
PostgreSQL instance that holds application data also stores workflow
checkpoints — there is no Redis anywhere in the system.

Tables managed by the checkpointer live in the public schema with the
``langgraph_`` prefix and are created via :func:`AsyncPostgresSaver.setup`.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from backend.config import Settings


@asynccontextmanager
async def open_checkpointer(settings: Settings) -> AsyncIterator[AsyncPostgresSaver]:
    """Open and initialize the async PostgreSQL checkpointer."""
    async with AsyncPostgresSaver.from_conn_string(
        settings.postgres_dsn_psycopg
    ) as saver:
        # ``setup`` is idempotent and creates the langgraph_* tables.
        await saver.setup()
        yield saver
