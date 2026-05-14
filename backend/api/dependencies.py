"""FastAPI dependency providers (DI).

Long-lived singletons (engine, settings, LLM client, OpenProject client,
workflow graph) are attached to ``app.state`` during the application
lifespan and accessed per-request via these dependency functions.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import Settings
from backend.persistence.database import Database
from backend.repositories.analysis_repository import AnalysisRepository
from backend.security.credentials import CredentialVault
from backend.workflows.engine import WorkflowEngine


# ---------------------------------------------------------------------------
# State accessors
# ---------------------------------------------------------------------------
def get_settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


def get_database(request: Request) -> Database:
    return request.app.state.database  # type: ignore[no-any-return]


def get_vault(request: Request) -> CredentialVault:
    return request.app.state.vault  # type: ignore[no-any-return]


def get_workflow_engine(request: Request) -> WorkflowEngine:
    return request.app.state.workflow_engine  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Per-request scoped dependencies
# ---------------------------------------------------------------------------
async def get_db_session(
    database: Annotated[Database, Depends(get_database)],
) -> AsyncIterator[AsyncSession]:
    async for session in database.session():
        yield session


async def get_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AnalysisRepository:
    return AnalysisRepository(session)


SettingsDep = Annotated[Settings, Depends(get_settings)]
DatabaseDep = Annotated[Database, Depends(get_database)]
VaultDep = Annotated[CredentialVault, Depends(get_vault)]
WorkflowDep = Annotated[WorkflowEngine, Depends(get_workflow_engine)]
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
RepoDep = Annotated[AnalysisRepository, Depends(get_repository)]
