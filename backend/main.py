"""FastAPI application entrypoint.

Lifespan responsibilities:
- configure structured logging
- instantiate singletons (settings, database, vault, services, agents)
- open the PostgreSQL LangGraph checkpointer
- compile the workflow graph and expose a ``WorkflowEngine``
- ensure clean shutdown of HTTP clients and DB engines
"""

from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.agents.diagram import DiagramAgent
from backend.agents.migration import MigrationAgent
from backend.agents.modeling import ModelingAgent
from backend.agents.openproject_agent import OpenProjectAgent
from backend.agents.performance import PerformanceAgent
from backend.agents.project_analysis import ProjectAnalysisAgent
from backend.agents.security import SecurityAgent
from backend.api.middleware import RequestContextMiddleware
from backend.api.routes import analysis_router
from backend.config import Settings, get_settings
from backend.domain.exceptions import (
    AnalysisNotFoundError,
    DomainError,
    InvalidApprovalStateError,
    OpenProjectError,
)
from backend.observability.logging import configure_logging, get_logger
from backend.persistence.database import Database
from backend.security.credentials import CredentialVault
from backend.security.sanitizer import sanitize_string
from backend.services.database.connector import DatabaseConnector
from backend.services.database.introspector import DatabaseIntrospector
from backend.services.llm.gemini import GeminiService
from backend.services.rendering.mermaid import MermaidRenderer
from backend.services.rendering.sql_generator import SqlGenerator
from backend.workflows.checkpointer import open_checkpointer
from backend.workflows.engine import WorkflowEngine
from backend.workflows.graph import build_analysis_graph
from backend.workflows.nodes import WorkflowDeps


def _build_agents(
    settings: Settings,
    llm: GeminiService,
    mermaid: MermaidRenderer,
    sql_gen: SqlGenerator,
) -> dict[str, object]:
    return {
        "project_analysis": ProjectAnalysisAgent(llm),
        "modeling": ModelingAgent(llm),
        "performance": PerformanceAgent(llm),
        "security": SecurityAgent(llm),
        "diagram": DiagramAgent(llm, mermaid),
        "migration": MigrationAgent(llm, sql_gen),
        "openproject": OpenProjectAgent(
            llm,
            api_url=settings.OPENPROJECT_API_URL,
            timeout=settings.OPENPROJECT_TIMEOUT,
        ),
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = get_settings()
    configure_logging(settings)
    logger = get_logger("startup")

    stack = AsyncExitStack()
    await stack.__aenter__()
    try:
        # Persistence
        database = Database(settings)
        stack.push_async_callback(database.dispose)

        # Security
        vault = CredentialVault(settings)

        # LLM (Gemini only)
        llm = GeminiService(settings)

        # Renderers
        mermaid = MermaidRenderer()
        sql_gen = SqlGenerator()

        # Customer DB connector / introspector
        connector = DatabaseConnector()
        introspector = DatabaseIntrospector(connector)

        # Agents (OpenProject client is built per-request inside the agent)
        agents = _build_agents(settings, llm, mermaid, sql_gen)

        # LangGraph checkpointer + graph
        checkpointer = await stack.enter_async_context(open_checkpointer(settings))

        deps = WorkflowDeps(
            database=database,
            credential_vault=vault,
            introspector=introspector,
            project_analysis_agent=agents["project_analysis"],  # type: ignore[arg-type]
            modeling_agent=agents["modeling"],  # type: ignore[arg-type]
            performance_agent=agents["performance"],  # type: ignore[arg-type]
            security_agent=agents["security"],  # type: ignore[arg-type]
            diagram_agent=agents["diagram"],  # type: ignore[arg-type]
            migration_agent=agents["migration"],  # type: ignore[arg-type]
            openproject_agent=agents["openproject"],  # type: ignore[arg-type]
        )
        graph = build_analysis_graph(deps, checkpointer)
        engine = WorkflowEngine(graph)

        # Publish to app state
        app.state.settings = settings
        app.state.database = database
        app.state.vault = vault
        app.state.workflow_engine = engine

        logger.info("app.startup_complete")
        yield
    finally:
        await stack.__aexit__(None, None, None)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="db_gerador backend",
        description="AI-powered database architecture analysis (Gemini + LangGraph).",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.API_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextMiddleware)

    app.include_router(analysis_router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # ------------------------------------------------------------------
    # Global exception handlers (sanitized responses)
    # ------------------------------------------------------------------
    @app.exception_handler(AnalysisNotFoundError)
    async def _not_found(_: Request, exc: AnalysisNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": sanitize_string(str(exc))})

    @app.exception_handler(InvalidApprovalStateError)
    async def _bad_state(_: Request, exc: InvalidApprovalStateError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": sanitize_string(str(exc))})

    @app.exception_handler(OpenProjectError)
    async def _openproject(_: Request, exc: OpenProjectError) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content={"detail": sanitize_string(str(exc)), "kind": "openproject_error"},
        )

    @app.exception_handler(DomainError)
    async def _domain(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": sanitize_string(str(exc)), "kind": exc.__class__.__name__},
        )

    return app


app = create_app()
