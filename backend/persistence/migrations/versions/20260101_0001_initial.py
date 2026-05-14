"""initial schema

Revision ID: 20260101_0001
Revises:
Create Date: 2026-01-01 00:00:00
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from backend.config import get_settings

revision: str = "20260101_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCHEMA = get_settings().POSTGRES_SCHEMA


def upgrade() -> None:
    # Ensure the target schema exists; tables are placed inside it.
    op.execute(f'CREATE SCHEMA IF NOT EXISTS "{_SCHEMA}"')

    op.create_table(
        "analysis_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_email", sa.String(length=320), nullable=False),
        sa.Column("openproject_task_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("approval_state", sa.String(length=32), nullable=False),
        sa.Column("rejection_feedback", sa.Text(), nullable=True),
        sa.Column("errors", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("result_snapshot", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("openproject_token_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_analysis_sessions_user_email", "analysis_sessions", ["user_email"])
    op.create_index("ix_analysis_sessions_op_task_id", "analysis_sessions", ["openproject_task_id"])

    op.create_table(
        "analysis_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("artifact_type", sa.String(length=64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("artifact_metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_analysis_artifacts_session_id", "analysis_artifacts", ["session_id"])

    op.create_table(
        "analysis_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_name", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_analysis_logs_session_id", "analysis_logs", ["session_id"])

    op.create_table(
        "encrypted_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_encrypted_credentials_session_id", "encrypted_credentials", ["session_id"])
    op.create_index("ix_encrypted_credentials_expires_at", "encrypted_credentials", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_encrypted_credentials_expires_at", table_name="encrypted_credentials")
    op.drop_index("ix_encrypted_credentials_session_id", table_name="encrypted_credentials")
    op.drop_table("encrypted_credentials")
    op.drop_index("ix_analysis_logs_session_id", table_name="analysis_logs")
    op.drop_table("analysis_logs")
    op.drop_index("ix_analysis_artifacts_session_id", table_name="analysis_artifacts")
    op.drop_table("analysis_artifacts")
    op.drop_index("ix_analysis_sessions_op_task_id", table_name="analysis_sessions")
    op.drop_index("ix_analysis_sessions_user_email", table_name="analysis_sessions")
    op.drop_table("analysis_sessions")
