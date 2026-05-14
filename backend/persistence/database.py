"""Async SQLAlchemy engine and session factory for application persistence."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.config import Settings


class Database:
    """Owns the application's async engine + session factory."""

    def __init__(self, settings: Settings) -> None:
        self._engine: AsyncEngine = create_async_engine(
            settings.postgres_dsn_async,
            pool_size=settings.POSTGRES_POOL_SIZE,
            max_overflow=settings.POSTGRES_MAX_OVERFLOW,
            pool_pre_ping=True,
            echo=False,
            connect_args={
                # Pin every asyncpg connection to the configured schema so
                # ORM queries resolve unqualified table names there.
                "server_settings": {"search_path": settings.POSTGRES_SCHEMA},
            },
        )
        self._session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self._engine,
            expire_on_commit=False,
            autoflush=False,
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self._session_factory() as session:
            yield session

    async def dispose(self) -> None:
        await self._engine.dispose()
