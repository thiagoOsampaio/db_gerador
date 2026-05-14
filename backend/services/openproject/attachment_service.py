"""OpenProject attachment upload service."""

from __future__ import annotations

import json
from typing import Any

import httpx

from backend.domain.exceptions import OpenProjectError
from backend.domain.models.openproject import TaskAttachment
from backend.observability.logging import get_logger
from backend.services.openproject.client import OpenProjectClient

_logger = get_logger(__name__)


class OpenProjectAttachmentService:
    def __init__(self, client: OpenProjectClient) -> None:
        self._client = client

    async def upload(
        self,
        *,
        work_package_id: str,
        filename: str,
        content: bytes,
        content_type: str = "application/octet-stream",
        description: str | None = None,
    ) -> TaskAttachment:
        """Upload an attachment directly to a work package.

        Uses the multipart form per OpenProject API spec, where the
        ``metadata`` part carries JSON describing the attachment and the
        ``file`` part carries the binary payload.
        """
        metadata = {
            "fileName": filename,
            "description": {"raw": description or ""},
        }
        files = {
            "metadata": (
                None,
                json.dumps(metadata),
                "application/json",
            ),
            "file": (filename, content, content_type),
        }

        # tenacity-retried plain request used for normal flows; here we use
        # a one-shot multipart call to keep the API simple.
        try:
            response = await self._client._client.post(  # noqa: SLF001
                f"/api/v3/work_packages/{work_package_id}/attachments",
                files=files,
            )
        except httpx.HTTPError as exc:
            raise OpenProjectError(f"Upload failed: {type(exc).__name__}") from exc

        if response.status_code >= 400:
            raise OpenProjectError(
                f"Attachment upload returned {response.status_code}",
                status_code=response.status_code,
            )

        data = response.json()
        _logger.info(
            "openproject.attachment_uploaded",
            work_package_id=work_package_id,
            filename=filename,
            size=len(content),
        )
        return TaskAttachment(
            filename=filename,
            content_type=content_type,
            size_bytes=len(content),
            description=description,
            attachment_id=_extract_id(data),
        )


def _extract_id(data: dict[str, Any]) -> int | None:
    if "id" in data:
        return int(data["id"])
    self_link = (data.get("_links") or {}).get("self") or {}
    href = self_link.get("href") or ""
    parts = href.rstrip("/").split("/")
    if parts and parts[-1].isdigit():
        return int(parts[-1])
    return None
