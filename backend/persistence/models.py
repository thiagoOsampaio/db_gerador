"""SQLAlchemy ORM models for application persistence (PostgreSQL).

Customer credentials are stored encrypted as bytes with an expiration
timestamp; the encryption key lives in ``Settings`` and is loaded from
env vars only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    LargeBinary,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from backend.domain.enums import AnalysisStatus, ApprovalState, ArtifactType


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class AnalysisSessionModel(Base):
    __tablename__ = "analysis_sessions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_email: Mapped[str] = mapped_column(String(320), index=True)
    openproject_task_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[AnalysisStatus] = mapped_column(
        String(64), default=AnalysisStatus.PENDING
    )
    approval_state: Mapped[ApprovalState] = mapped_column(
        String(32), default=ApprovalState.PENDING
    )
    rejection_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    errors: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    result_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    openproject_token_ciphertext: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    artifacts: Mapped[list[AnalysisArtifactModel]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    logs: Mapped[list[AnalysisLogModel]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    credentials: Mapped[list[EncryptedCredentialModel]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class AnalysisArtifactModel(Base):
    __tablename__ = "analysis_artifacts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_sessions.id", ondelete="CASCADE"), index=True
    )
    artifact_type: Mapped[ArtifactType] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(Text)
    artifact_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    session: Mapped[AnalysisSessionModel] = relationship(back_populates="artifacts")


class AnalysisLogModel(Base):
    __tablename__ = "analysis_logs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_sessions.id", ondelete="CASCADE"), index=True
    )
    agent_name: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    session: Mapped[AnalysisSessionModel] = relationship(back_populates="logs")


class EncryptedCredentialModel(Base):
    """Encrypted customer-database credentials with TTL."""

    __tablename__ = "encrypted_credentials"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_sessions.id", ondelete="CASCADE"), index=True
    )
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    session: Mapped[AnalysisSessionModel] = relationship(back_populates="credentials")
