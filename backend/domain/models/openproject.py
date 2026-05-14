"""OpenProject update payload models."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class TaskComment(BaseModel):
    model_config = ConfigDict(frozen=True)

    body: str  # Markdown / textile per OpenProject configuration
    author_email: str | None = None


class TaskAttachment(BaseModel):
    model_config = ConfigDict(frozen=True)

    filename: str
    content_type: str
    size_bytes: int
    description: str | None = None
    attachment_id: int | None = None  # populated after upload


class OpenProjectTaskUpdate(BaseModel):
    """Result of an OpenProject update action."""

    model_config = ConfigDict(frozen=True)

    task_id: str
    comment: TaskComment | None = None
    attachments: list[TaskAttachment] = Field(default_factory=list)
    status_transition: str | None = None
    updated_at: datetime = Field(default_factory=_utcnow)
    success: bool = True
    error: str | None = None
