"""``/analysis`` HTTP routes.

The route layer is intentionally thin: it validates inputs, encrypts the
customer database password into the vault, persists session metadata,
and delegates orchestration to :class:`WorkflowEngine`.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from backend.api.dependencies import (
    RepoDep,
    SessionDep,
    VaultDep,
    WorkflowDep,
)
from backend.api.schemas import (
    AnalysisResponse,
    DiagramResponse,
    RejectionRequest,
    RetakeAnalysisRequest,
    SqlResponse,
    StartAnalysisRequest,
    StartAnalysisResponse,
    StatusResponse,
)
from backend.domain.enums import (
    AnalysisStatus,
    ApprovalState,
    ArtifactType,
)
from backend.domain.exceptions import (
    AnalysisNotFoundError,
    InvalidApprovalStateError,
)
from backend.domain.models.artifacts import DiagramArtifact, SqlArtifact
from backend.domain.models.database import DatabaseConnection
from backend.observability.logging import get_logger

router = APIRouter(prefix="/analysis", tags=["analysis"])
_logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# POST /analysis/start
# ---------------------------------------------------------------------------
@router.post(
    "/start",
    response_model=StartAnalysisResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_analysis(
    payload: StartAnalysisRequest,
    background: BackgroundTasks,
    repo: RepoDep,
    session: SessionDep,
    vault: VaultDep,
    workflow: WorkflowDep,
) -> StartAnalysisResponse:
    """Create a session, encrypt credentials, and launch the workflow."""
    session_id = await _bootstrap_session(payload, repo, session, vault)

    background.add_task(_run_workflow, workflow, session_id, payload)

    _logger.info(
        "analysis.started",
        session_id=str(session_id),
        user_email=str(payload.user_email),
        openproject_task_id=payload.openproject_task_id,
    )
    return StartAnalysisResponse(
        session_id=session_id,
        status=AnalysisStatus.PENDING,
        approval_state=ApprovalState.PENDING,
    )


async def _bootstrap_session(
    payload: StartAnalysisRequest,
    repo: RepoDep,
    session: SessionDep,
    vault: VaultDep,
) -> UUID:
    """Persist a new session row + encrypted credential; return session id.

    Shared by ``POST /analysis/start`` and ``POST /analysis/retake``.
    """
    # 1. Build a DatabaseConnection — password held as SecretStr.
    connection = DatabaseConnection(
        database_type=payload.database_type,
        host=payload.database_host,
        port=payload.database_port,
        database_name=payload.database_name,
        username=payload.database_username,
        password=payload.database_password,
    )

    # 2. Persist session row with the encrypted OpenProject token.
    op_token_ciphertext = vault.encrypt_token(
        payload.openproject_token.get_secret_value()
    )
    session_row = await repo.create_session(
        user_email=str(payload.user_email),
        openproject_task_id=payload.openproject_task_id,
        openproject_token_ciphertext=op_token_ciphertext,
    )

    # 3. Encrypt + store the customer DB credential.
    encrypted = vault.encrypt(connection)
    await repo.store_credential(
        session_id=session_row.id, credential=encrypted
    )
    await session.commit()
    return session_row.id


# ---------------------------------------------------------------------------
# POST /analysis/retake
# ---------------------------------------------------------------------------
@router.post(
    "/retake",
    response_model=StartAnalysisResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retake_analysis(
    payload: RetakeAnalysisRequest,
    background: BackgroundTasks,
    repo: RepoDep,
    session: SessionDep,
    vault: VaultDep,
    workflow: WorkflowDep,
) -> StartAnalysisResponse:
    """Disparar uma nova análise (retomada) na mesma task do OpenProject.

    O DBA usa esta rota quando, ao ler o comentário anterior na task, nota
    que a abordagem proposta não resolve adequadamente o problema. Uma
    sessão totalmente nova é criada, todo o fluxo executado do zero e ao
    final um novo comentário (com cabeçalho “Nova abordagem”) é anexado
    à mesma task, preservando o histórico.
    """
    # Vincula esta retomada à sessão mais recente da mesma task (apenas
    # para auditoria / referência no comentário).
    parent_session_id = await repo.latest_session_for_task(
        payload.openproject_task_id
    )

    new_session_id = await _bootstrap_session(payload, repo, session, vault)

    background.add_task(
        _run_workflow,
        workflow,
        new_session_id,
        payload,
        True,
        parent_session_id,
    )

    _logger.info(
        "analysis.retake_started",
        session_id=str(new_session_id),
        parent_session_id=(
            str(parent_session_id) if parent_session_id else None
        ),
        openproject_task_id=payload.openproject_task_id,
    )
    return StartAnalysisResponse(
        session_id=new_session_id,
        status=AnalysisStatus.PENDING,
        approval_state=ApprovalState.PENDING,
        message="Retake started",
    )


async def _run_workflow(
    workflow: WorkflowDep,  # type: ignore[valid-type]
    session_id: UUID,
    payload: StartAnalysisRequest,
    is_retake: bool = False,
    parent_session_id: UUID | None = None,
) -> None:
    try:
        await workflow.start(  # type: ignore[attr-defined]
            session_id=session_id,
            user_email=str(payload.user_email),
            openproject_task_id=payload.openproject_task_id,
            developer_request=payload.developer_request,
            framework_name=payload.framework_name,
            orm_name=payload.orm_name,
            project_metadata=payload.project_metadata,
            user_entities=[e.name for e in payload.entities],
            user_relationships=[
                f"{r.source_entity}->{r.target_entity}:{r.cardinality}"
                for r in payload.relationships
            ],
            is_retake=is_retake,
            parent_session_id=parent_session_id,
        )
    except asyncio.CancelledError:  # pragma: no cover
        raise
    except Exception:  # noqa: BLE001
        # ``exception`` emits the full traceback so structured logs no
        # longer hide the real failure behind a bare exception name.
        _logger.exception(
            "analysis.workflow_failed",
            session_id=str(session_id),
        )


# ---------------------------------------------------------------------------
# GET /analysis/{id}
# ---------------------------------------------------------------------------
@router.get("/{session_id}", response_model=AnalysisResponse)
async def get_analysis(session_id: UUID, repo: RepoDep) -> AnalysisResponse:
    try:
        row = await repo.get_session(session_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    snapshot = row.result_snapshot or {}
    diagram_row = await repo.latest_artifact(session_id, ArtifactType.DIAGRAM_MERMAID)
    sql_row = await repo.latest_artifact(session_id, ArtifactType.SQL_DDL)

    return AnalysisResponse(
        session_id=row.id,
        user_email=row.user_email,
        openproject_task_id=row.openproject_task_id,
        status=row.status,
        approval_state=row.approval_state,
        rejection_feedback=row.rejection_feedback,
        errors=list(row.errors or []),
        diagram=(
            DiagramArtifact(content=diagram_row.content, summary=(diagram_row.artifact_metadata or {}).get("summary"))
            if diagram_row
            else None
        ),
        sql_artifact=(
            SqlArtifact(ddl=sql_row.content, summary=(sql_row.artifact_metadata or {}).get("summary"))
            if sql_row
            else None
        ),
        performance_recommendations=snapshot.get("performance_recommendations", []),
        security_recommendations=snapshot.get("security_recommendations", []),
        openproject_update=snapshot.get("openproject_update"),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# ---------------------------------------------------------------------------
# GET /analysis/{id}/status
# ---------------------------------------------------------------------------
@router.get("/{session_id}/status", response_model=StatusResponse)
async def get_status(session_id: UUID, repo: RepoDep) -> StatusResponse:
    try:
        row = await repo.get_session(session_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return StatusResponse(
        session_id=row.id,
        status=row.status,
        approval_state=row.approval_state,
        rejection_feedback=row.rejection_feedback,
        errors=list(row.errors or []),
        updated_at=row.updated_at,
    )


# ---------------------------------------------------------------------------
# GET /analysis/{id}/diagram
# ---------------------------------------------------------------------------
@router.get("/{session_id}/diagram", response_model=DiagramResponse)
async def get_diagram(session_id: UUID, repo: RepoDep) -> DiagramResponse:
    artifact = await repo.latest_artifact(session_id, ArtifactType.DIAGRAM_MERMAID)
    if not artifact:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Diagram not available yet")

    # Recupera o snapshot da sessão para extrair as medidas que a IA
    # propõe como solução ao problema descrito na task.
    try:
        row = await repo.get_session(session_id)
        snapshot: dict[str, Any] = row.result_snapshot or {}
    except AnalysisNotFoundError:
        snapshot = {}

    proposed_actions, rationale = _summarize_proposed_actions(snapshot)

    return DiagramResponse(
        session_id=session_id,
        content=artifact.content,
        summary=(artifact.artifact_metadata or {}).get("summary"),
        rationale=rationale,
        proposed_actions=proposed_actions,
    )


def _summarize_proposed_actions(
    snapshot: dict[str, Any],
) -> tuple[list[str], str | None]:
    """Extract narrative + bullet-style actions from the result snapshot.

    The snapshot is the JSON-serialised :class:`AnalysisResult` persisted
    by the ``merge_results`` node, so all fields are dictionaries.
    """
    rationale_parts: list[str] = []
    ir = snapshot.get("project_ir") or {}
    rm = snapshot.get("relational_model") or {}
    if isinstance(ir, dict) and ir.get("notes"):
        rationale_parts.append(str(ir["notes"]).strip())
    if isinstance(rm, dict) and rm.get("notes"):
        rationale_parts.append(str(rm["notes"]).strip())
    rationale = "\n\n".join(rationale_parts) if rationale_parts else None

    actions: list[str] = []
    if isinstance(rm, dict):
        for table in rm.get("tables") or []:
            if not isinstance(table, dict):
                continue
            name = table.get("name")
            desc = (table.get("description") or "").strip()
            if name and desc:
                actions.append(f"Tabela `{name}`: {desc}")
            elif name:
                actions.append(f"Tabela `{name}`")
    for rec in snapshot.get("performance_recommendations") or []:
        if isinstance(rec, dict) and rec.get("title"):
            actions.append(f"Performance — {rec['title']}")
    for rec in snapshot.get("security_recommendations") or []:
        if isinstance(rec, dict) and rec.get("title"):
            actions.append(f"Segurança — {rec['title']}")
    return actions, rationale


# ---------------------------------------------------------------------------
# GET /analysis/{id}/sql
# ---------------------------------------------------------------------------
@router.get("/{session_id}/sql", response_model=SqlResponse)
async def get_sql(session_id: UUID, repo: RepoDep) -> SqlResponse:
    artifact = await repo.latest_artifact(session_id, ArtifactType.SQL_DDL)
    if not artifact:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "SQL not available yet")
    alembic = await repo.latest_artifact(session_id, ArtifactType.ALEMBIC_MIGRATION)
    return SqlResponse(
        session_id=session_id,
        ddl=artifact.content,
        alembic_revision=alembic.content if alembic else None,
        summary=(artifact.artifact_metadata or {}).get("summary"),
    )


# ---------------------------------------------------------------------------
# GET /analysis/{id}/approve
# ---------------------------------------------------------------------------
# The approver's identity is the same ``user_email`` supplied in
# ``POST /analysis/start`` and persisted in the session row, so this
# endpoint takes no body and is safe as an idempotent GET trigger.
@router.get("/{session_id}/approve", response_model=StatusResponse)
async def approve_analysis(
    session_id: UUID,
    repo: RepoDep,
    session: SessionDep,
    workflow: WorkflowDep,
    background: BackgroundTasks,
) -> StatusResponse:
    try:
        row = await repo.get_session(session_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    if row.status != AnalysisStatus.AWAITING_APPROVAL:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Session is in status {row.status}, not awaiting approval",
        )

    await repo.update_approval(session_id, ApprovalState.APPROVED)
    await session.commit()

    background.add_task(_resume_after_approval, workflow, session_id, approve=True)

    _logger.info("analysis.approved", session_id=str(session_id), user=row.user_email)
    return StatusResponse(
        session_id=row.id,
        status=row.status,
        approval_state=ApprovalState.APPROVED,
        updated_at=row.updated_at,
    )


# ---------------------------------------------------------------------------
# POST /analysis/{id}/reject
# ---------------------------------------------------------------------------
@router.post("/{session_id}/reject", response_model=StatusResponse)
async def reject_analysis(
    session_id: UUID,
    body: RejectionRequest,
    repo: RepoDep,
    session: SessionDep,
    workflow: WorkflowDep,
    background: BackgroundTasks,
) -> StatusResponse:
    try:
        row = await repo.get_session(session_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    if row.status != AnalysisStatus.AWAITING_APPROVAL:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Session is in status {row.status}, not awaiting approval",
        )

    await repo.update_approval(session_id, ApprovalState.REJECTED, body.feedback)
    await session.commit()

    background.add_task(
        _resume_after_approval,
        workflow,
        session_id,
        approve=False,
        feedback=body.feedback,
    )

    _logger.info("analysis.rejected", session_id=str(session_id), user=row.user_email)
    return StatusResponse(
        session_id=row.id,
        status=row.status,
        approval_state=ApprovalState.REJECTED,
        rejection_feedback=body.feedback,
        updated_at=row.updated_at,
    )


async def _resume_after_approval(
    workflow: WorkflowDep,  # type: ignore[valid-type]
    session_id: UUID,
    *,
    approve: bool,
    feedback: str | None = None,
) -> None:
    try:
        if approve:
            await workflow.approve(session_id)  # type: ignore[attr-defined]
        else:
            await workflow.reject(session_id, feedback)  # type: ignore[attr-defined]
    except InvalidApprovalStateError as exc:
        _logger.warning("analysis.resume_invalid_state", session_id=str(session_id), error=str(exc))
    except Exception:  # noqa: BLE001
        _logger.exception(
            "analysis.resume_failed",
            session_id=str(session_id),
        )
