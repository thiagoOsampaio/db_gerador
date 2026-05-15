"""Node implementations for the analysis LangGraph workflow.

Nodes are pure async callables that take the current ``WorkflowState``
and return a partial state update. They are wired together by
:func:`build_analysis_graph`.

Dependencies are bundled inside :class:`WorkflowDeps` and injected once
at graph-build time, keeping nodes free of global state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from langgraph.types import Send

from backend.agents.base import AgentContext
from backend.agents.diagram import DiagramAgent
from backend.agents.migration import MigrationAgent
from backend.agents.modeling import ModelingAgent
from backend.agents.openproject_agent import OpenProjectAgent, OpenProjectAgentInput
from backend.agents.performance import PerformanceAgent
from backend.agents.project_analysis import ProjectAnalysisAgent, ProjectAnalysisInput
from backend.agents.security import SecurityAgent, SecurityAgentInput
from backend.domain.enums import AnalysisStatus, ApprovalState, ArtifactType
from backend.domain.exceptions import (
    AgentExecutionError,
    SchemaIntrospectionError,
)
from backend.domain.models.analysis import AnalysisResult
from backend.observability.logging import get_logger
from backend.persistence.database import Database
from backend.repositories.analysis_repository import AnalysisRepository
from backend.security.credentials import CredentialVault
from backend.services.database.introspector import DatabaseIntrospector
from backend.services.openproject.client import OpenProjectClient
from backend.services.openproject.task_service import OpenProjectTaskService
from backend.workflows.state import WorkflowState

_logger = get_logger(__name__)


@dataclass
class WorkflowDeps:
    """All services a graph node may need."""

    database: Database
    credential_vault: CredentialVault
    introspector: DatabaseIntrospector
    project_analysis_agent: ProjectAnalysisAgent
    modeling_agent: ModelingAgent
    performance_agent: PerformanceAgent
    security_agent: SecurityAgent
    diagram_agent: DiagramAgent
    migration_agent: MigrationAgent
    openproject_agent: OpenProjectAgent
    # OpenProject HTTP wiring — clients are built per-request inside the
    # nodes using the per-session decrypted token.
    openproject_api_url: str
    openproject_timeout: int = 30


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ctx(state: dict[str, Any]) -> AgentContext:
    return AgentContext(
        session_id=state["session_id"],
        user_email=state["user_email"],
    )


async def _persist_status(
    deps: WorkflowDeps,
    state: dict[str, Any],
    status: AnalysisStatus,
) -> None:
    async for session in deps.database.session():
        repo = AnalysisRepository(session)
        await repo.update_status(UUID(state["session_id"]), status)
        await session.commit()
        break


async def _log_event(
    deps: WorkflowDeps,
    state: dict[str, Any],
    agent_name: str,
    action: str,
    payload: dict[str, Any] | None = None,
) -> None:
    async for session in deps.database.session():
        repo = AnalysisRepository(session)
        await repo.log_event(
            session_id=UUID(state["session_id"]),
            agent_name=agent_name,
            action=action,
            payload=payload,
        )
        await session.commit()
        break


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------
def make_validate_input(deps: WorkflowDeps):
    async def validate_input(state: WorkflowState) -> dict[str, Any]:  # type: ignore[name-defined]
        _logger.info("workflow.node.enter", node="validate_input", keys=list(state.keys()))
        await _persist_status(deps, state, AnalysisStatus.INTROSPECTING)

        session_id = UUID(state["session_id"])
        # Fetch encrypted credential + OpenProject token from DB.
        async for db_session in deps.database.session():
            repo = AnalysisRepository(db_session)
            cred_row = await repo.get_active_credential(session_id)
            if cred_row is None:
                raise SchemaIntrospectionError("No active credential for session")
            connection = deps.credential_vault.decrypt(
                cred_row.ciphertext, cred_row.expires_at
            )
            session_row = await repo.get_session(session_id)
            token_ct = session_row.openproject_token_ciphertext
            break

        # Introspect the customer database (read-only).
        schema = await deps.introspector.introspect(connection)
        # ``connection`` falls out of scope here; password is GC'd.
        await _log_event(deps, state, "introspector", "schema_extracted",
                         {"tables": len(schema.tables)})

        # Fetch the OpenProject task description so the developer's
        # request and the ticket's intent both feed the agents.
        task_description: str | None = None
        if token_ct:
            try:
                token = deps.credential_vault.decrypt_token(token_ct)
                async with OpenProjectClient(
                    api_url=deps.openproject_api_url,
                    token=token,
                    timeout=deps.openproject_timeout,
                ) as client:
                    tasks = OpenProjectTaskService(client)
                    wp = await tasks.get_work_package(state["openproject_task_id"])
                desc = (wp.get("description") or {})
                if isinstance(desc, dict):
                    task_description = desc.get("raw") or desc.get("plain") or None
                else:
                    task_description = str(desc) or None
                await _log_event(
                    deps, state, "openproject", "task_fetched",
                    {"has_description": bool(task_description)},
                )
            except Exception:  # noqa: BLE001
                # Non-fatal: the workflow can still run on the developer
                # request alone. The traceback is logged for diagnosis.
                _logger.exception(
                    "workflow.openproject_fetch_failed",
                    session_id=str(session_id),
                )

        return {
            "schema_snapshot": schema,
            "openproject_task_description": task_description,
            "status": AnalysisStatus.ANALYZING_PROJECT,
        }

    return validate_input


def make_analyze_project(deps: WorkflowDeps):
    async def analyze_project(state: WorkflowState) -> dict[str, Any]:  # type: ignore[name-defined]
        _logger.info("workflow.node.enter", node="analyze_project", keys=list(state.keys()))
        await _persist_status(deps, state, AnalysisStatus.ANALYZING_PROJECT)
        payload = ProjectAnalysisInput(
            framework_name=state.get("framework_name"),
            orm_name=state.get("orm_name"),
            project_metadata=state.get("project_metadata") or {},
            schema_snapshot=state.get("schema_snapshot"),
            user_entities=state.get("user_entities") or [],
            user_relationships=state.get("user_relationships") or [],
            developer_request=state.get("developer_request"),
            openproject_task_description=state.get("openproject_task_description"),
            rejection_feedback=state.get("rejection_feedback"),
        )
        ir = await deps.project_analysis_agent.run(payload, _ctx(state))
        await _log_event(deps, state, "project_analysis", "done",
                         {"entities": len(ir.entities)})
        # Clear approval-loop fields so the next await_approval starts fresh.
        return {
            "project_ir": ir,
            "status": AnalysisStatus.MODELING,
            "approval_state": ApprovalState.PENDING,
            "rejection_feedback": None,
        }

    return analyze_project


def make_model_schema(deps: WorkflowDeps):
    async def model_schema(state: WorkflowState) -> dict[str, Any]:  # type: ignore[name-defined]
        _logger.info("workflow.node.enter", node="model_schema", keys=list(state.keys()))
        await _persist_status(deps, state, AnalysisStatus.MODELING)
        ir = state.get("project_ir")
        if ir is None:
            raise AgentExecutionError("modeling", "Missing project_ir")
        model = await deps.modeling_agent.run(ir, _ctx(state))
        await _log_event(deps, state, "modeling", "done",
                         {"tables": len(model.tables)})
        return {"relational_model": model}

    return model_schema


def make_analyze_performance(deps: WorkflowDeps):
    async def analyze_performance(state: WorkflowState) -> dict[str, Any]:  # type: ignore[name-defined]
        _logger.info("workflow.node.enter", node="analyze_performance", keys=list(state.keys()))
        await _persist_status(deps, state, AnalysisStatus.ANALYZING_PERFORMANCE)
        model = state.get("relational_model")
        if model is None:
            raise AgentExecutionError("performance", "Missing relational_model")
        out = await deps.performance_agent.run(model, _ctx(state))
        await _log_event(deps, state, "performance", "done",
                         {"recommendations": len(out.recommendations)})
        return {"performance_recommendations": out.recommendations}

    return analyze_performance


def make_analyze_security(deps: WorkflowDeps):
    async def analyze_security(state: WorkflowState) -> dict[str, Any]:  # type: ignore[name-defined]
        _logger.info("workflow.node.enter", node="analyze_security", keys=list(state.keys()))
        await _persist_status(deps, state, AnalysisStatus.ANALYZING_SECURITY)
        model = state.get("relational_model")
        if model is None:
            raise AgentExecutionError("security", "Missing relational_model")
        payload = SecurityAgentInput(
            relational_model=model,
            schema_snapshot=state.get("schema_snapshot"),
        )
        out = await deps.security_agent.run(payload, _ctx(state))
        await _log_event(deps, state, "security", "done",
                         {"recommendations": len(out.recommendations)})
        return {"security_recommendations": out.recommendations}

    return analyze_security


def make_merge_results(deps: WorkflowDeps):
    async def merge_results(state: WorkflowState) -> dict[str, Any]:  # type: ignore[name-defined]
        _logger.info("workflow.node.enter", node="merge_results", keys=list(state.keys()))
        await _persist_status(deps, state, AnalysisStatus.MERGING)
        # The reducers already merged parallel results. Nothing else to do
        # except advance the status and persist a snapshot.
        result = AnalysisResult(
            schema_snapshot=state.get("schema_snapshot"),
            project_ir=state.get("project_ir"),
            relational_model=state.get("relational_model"),
            performance_recommendations=list(state.get("performance_recommendations") or []),
            security_recommendations=list(state.get("security_recommendations") or []),
        )
        async for db_session in deps.database.session():
            repo = AnalysisRepository(db_session)
            await repo.update_result_snapshot(
                UUID(state["session_id"]),
                result.model_dump(mode="json"),
            )
            await db_session.commit()
            break
        return {"status": AnalysisStatus.GENERATING_ERD}

    return merge_results


def make_generate_erd(deps: WorkflowDeps):
    async def generate_erd(state: WorkflowState) -> dict[str, Any]:  # type: ignore[name-defined]
        _logger.info("workflow.node.enter", node="generate_erd", keys=list(state.keys()))
        await _persist_status(deps, state, AnalysisStatus.GENERATING_ERD)
        model = state.get("relational_model")
        if model is None:
            raise AgentExecutionError("diagram", "Missing relational_model")
        artifact = await deps.diagram_agent.run(model, _ctx(state))
        async for db_session in deps.database.session():
            repo = AnalysisRepository(db_session)
            await repo.save_artifact(
                session_id=UUID(state["session_id"]),
                artifact_type=ArtifactType.DIAGRAM_MERMAID,
                content=artifact.content,
                metadata={"summary": artifact.summary},
            )
            await db_session.commit()
            break
        await _log_event(deps, state, "diagram", "rendered")
        # The graph stops here (interrupt_before=await_approval). Persist
        # ``AWAITING_APPROVAL`` now so polling clients see the correct
        # status before any node downstream of the interrupt runs.
        await _persist_status(deps, state, AnalysisStatus.AWAITING_APPROVAL)
        return {
            "diagram": artifact,
            "status": AnalysisStatus.AWAITING_APPROVAL,
        }

    return generate_erd


def make_await_approval(deps: WorkflowDeps):
    """Human-in-the-loop gate.

    LangGraph's :func:`langgraph.types.interrupt` would normally be used
    here, but we keep approval state explicit so the API layer can resume
    the graph via ``update_state``. This node short-circuits if approval
    is still pending: the runtime returns to the caller, and the API
    layer mutates ``approval_state`` then re-invokes the graph.
    """

    async def await_approval(state: WorkflowState) -> dict[str, Any]:  # type: ignore[name-defined]
        _logger.info("workflow.node.enter", node="await_approval", keys=list(state.keys()))
        await _persist_status(deps, state, AnalysisStatus.AWAITING_APPROVAL)
        approval = state.get("approval_state") or ApprovalState.PENDING
        await _log_event(deps, state, "workflow", "approval_check",
                         {"state": str(approval)})
        return {"approval_state": approval}

    return await_approval


def make_generate_sql(deps: WorkflowDeps):
    async def generate_sql(state: WorkflowState) -> dict[str, Any]:  # type: ignore[name-defined]
        _logger.info("workflow.node.enter", node="generate_sql", keys=list(state.keys()))
        await _persist_status(deps, state, AnalysisStatus.GENERATING_SQL)
        model = state.get("relational_model")
        if model is None:
            raise AgentExecutionError("migration", "Missing relational_model")
        out = await deps.migration_agent.run(model, _ctx(state))
        async for db_session in deps.database.session():
            repo = AnalysisRepository(db_session)
            await repo.save_artifact(
                session_id=UUID(state["session_id"]),
                artifact_type=ArtifactType.SQL_DDL,
                content=out.sql_artifact.ddl,
                metadata={"summary": out.sql_artifact.summary},
            )
            if out.sql_artifact.alembic_revision:
                await repo.save_artifact(
                    session_id=UUID(state["session_id"]),
                    artifact_type=ArtifactType.ALEMBIC_MIGRATION,
                    content=out.sql_artifact.alembic_revision,
                    metadata={},
                )
            await db_session.commit()
            break

        await _log_event(deps, state, "migration", "generated",
                         {"steps": len(out.migration_plan.steps)})
        return {
            "sql_artifact": out.sql_artifact,
            "migration_plan": out.migration_plan,
            "status": AnalysisStatus.UPDATING_OPENPROJECT,
        }

    return generate_sql


def make_update_openproject(deps: WorkflowDeps):
    async def update_openproject(state: WorkflowState) -> dict[str, Any]:  # type: ignore[name-defined]
        _logger.info("workflow.node.enter", node="update_openproject", keys=list(state.keys()))
        await _persist_status(deps, state, AnalysisStatus.UPDATING_OPENPROJECT)

        # Decrypt the per-user OpenProject token (persisted at /analysis/start).
        session_id = UUID(state["session_id"])
        async for db_session in deps.database.session():
            repo = AnalysisRepository(db_session)
            session_row = await repo.get_session(session_id)
            token_ct = session_row.openproject_token_ciphertext
            break
        if not token_ct:
            raise AgentExecutionError(
                "openproject",
                "Missing OpenProject token for session",
            )
        token = deps.credential_vault.decrypt_token(token_ct)

        result = AnalysisResult(
            schema_snapshot=state.get("schema_snapshot"),
            project_ir=state.get("project_ir"),
            relational_model=state.get("relational_model"),
            performance_recommendations=list(state.get("performance_recommendations") or []),
            security_recommendations=list(state.get("security_recommendations") or []),
            diagram=state.get("diagram"),
            migration_plan=state.get("migration_plan"),
            sql_artifact=state.get("sql_artifact"),
        )
        payload = OpenProjectAgentInput(
            task_id=state["openproject_task_id"],
            user_email=state["user_email"],
            openproject_token=token,
            result=result,
            developer_request=state.get("developer_request"),
        )
        update = await deps.openproject_agent.run(payload, _ctx(state))
        await _persist_status(deps, state, AnalysisStatus.COMPLETED)
        await _log_event(deps, state, "openproject", "updated",
                         {"success": update.success})
        return {"openproject_update": update, "status": AnalysisStatus.COMPLETED}

    return update_openproject


# ---------------------------------------------------------------------------
# Routing helpers
# ---------------------------------------------------------------------------
def fanout_to_parallel(state: WorkflowState) -> list[Send]:  # type: ignore[name-defined]
    """Fan out into performance + security branches.

    The payload forwarded to each branch must carry the full state — a
    bare ``{}`` would erase ``session_id``/``relational_model`` and crash
    the downstream nodes with ``KeyError`` on the next status update.
    """
    payload = dict(state)
    return [
        Send("analyze_performance", payload),
        Send("analyze_security", payload),
    ]


def route_after_approval(state: WorkflowState) -> str:  # type: ignore[name-defined]
    approval = state.get("approval_state") or ApprovalState.PENDING
    if approval == ApprovalState.APPROVED:
        return "generate_sql"
    if approval == ApprovalState.REJECTED:
        return "analyze_project"
    return "__end__"
