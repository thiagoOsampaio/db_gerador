"""Repository for ``AnalysisSession`` and related rows."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.enums import AnalysisStatus, ApprovalState, ArtifactType
from backend.domain.exceptions import AnalysisNotFoundError
from backend.persistence.models import (
    AnalysisArtifactModel,
    AnalysisLogModel,
    AnalysisSessionModel,
    EncryptedCredentialModel,
)
from backend.security.credentials import EncryptedCredential


class AnalysisRepository:
    """CRUD for analysis sessions, artifacts, logs, and encrypted creds."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------
    async def create_session(
        self,
        *,
        user_email: str,
        openproject_task_id: str,
        openproject_token_ciphertext: bytes | None = None,
    ) -> AnalysisSessionModel:
        row = AnalysisSessionModel(
            user_email=user_email,
            openproject_task_id=openproject_task_id,
            status=AnalysisStatus.PENDING,
            approval_state=ApprovalState.PENDING,
            errors=[],
            result_snapshot={},
            openproject_token_ciphertext=openproject_token_ciphertext,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_session(self, session_id: UUID) -> AnalysisSessionModel:
        row = await self._session.get(AnalysisSessionModel, session_id)
        if row is None:
            raise AnalysisNotFoundError(f"Analysis session {session_id} not found")
        return row

    async def update_status(
        self,
        session_id: UUID,
        status: AnalysisStatus,
    ) -> None:
        row = await self.get_session(session_id)
        row.status = status
        row.updated_at = datetime.now(tz=timezone.utc)

    async def update_approval(
        self,
        session_id: UUID,
        state: ApprovalState,
        feedback: str | None = None,
    ) -> None:
        row = await self.get_session(session_id)
        row.approval_state = state
        row.rejection_feedback = feedback
        row.updated_at = datetime.now(tz=timezone.utc)

    async def append_error(self, session_id: UUID, error: str) -> None:
        row = await self.get_session(session_id)
        errors = list(row.errors or [])
        errors.append(error)
        row.errors = errors

    async def update_result_snapshot(
        self,
        session_id: UUID,
        snapshot: dict[str, Any],
    ) -> None:
        row = await self.get_session(session_id)
        row.result_snapshot = snapshot

    # ------------------------------------------------------------------
    # Artifacts
    # ------------------------------------------------------------------
    async def save_artifact(
        self,
        *,
        session_id: UUID,
        artifact_type: ArtifactType,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> AnalysisArtifactModel:
        row = AnalysisArtifactModel(
            session_id=session_id,
            artifact_type=artifact_type,
            content=content,
            artifact_metadata=metadata or {},
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def latest_artifact(
        self,
        session_id: UUID,
        artifact_type: ArtifactType,
    ) -> AnalysisArtifactModel | None:
        stmt = (
            select(AnalysisArtifactModel)
            .where(
                AnalysisArtifactModel.session_id == session_id,
                AnalysisArtifactModel.artifact_type == artifact_type,
            )
            .order_by(AnalysisArtifactModel.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Logs
    # ------------------------------------------------------------------
    async def log_event(
        self,
        *,
        session_id: UUID,
        agent_name: str,
        action: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self._session.add(
            AnalysisLogModel(
                session_id=session_id,
                agent_name=agent_name,
                action=action,
                payload=payload or {},
            )
        )

    # ------------------------------------------------------------------
    # Encrypted credentials
    # ------------------------------------------------------------------
    async def store_credential(
        self,
        *,
        session_id: UUID,
        credential: EncryptedCredential,
    ) -> EncryptedCredentialModel:
        row = EncryptedCredentialModel(
            session_id=session_id,
            ciphertext=credential.ciphertext,
            expires_at=credential.expires_at,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_active_credential(
        self,
        session_id: UUID,
    ) -> EncryptedCredentialModel | None:
        stmt = (
            select(EncryptedCredentialModel)
            .where(
                EncryptedCredentialModel.session_id == session_id,
                EncryptedCredentialModel.expires_at > datetime.now(tz=timezone.utc),
            )
            .order_by(EncryptedCredentialModel.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def purge_expired_credentials(self) -> int:
        stmt = delete(EncryptedCredentialModel).where(
            EncryptedCredentialModel.expires_at <= datetime.now(tz=timezone.utc)
        )
        result = await self._session.execute(stmt)
        return result.rowcount or 0
