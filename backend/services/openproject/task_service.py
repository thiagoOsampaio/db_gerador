"""Work-package (task) operations: comments + status transitions."""

from __future__ import annotations

from typing import Any

from backend.observability.logging import get_logger
from backend.services.openproject.client import OpenProjectClient

_logger = get_logger(__name__)


class OpenProjectTaskService:
    def __init__(self, client: OpenProjectClient) -> None:
        self._client = client

    async def get_work_package(self, work_package_id: str) -> dict[str, Any]:
        response = await self._client.request("GET", f"/api/v3/work_packages/{work_package_id}")
        return response.json()

    async def add_comment(self, work_package_id: str, body_markdown: str) -> dict[str, Any]:
        payload = {"comment": {"raw": body_markdown}}
        response = await self._client.request(
            "POST",
            f"/api/v3/work_packages/{work_package_id}/activities",
            json=payload,
        )
        _logger.info("openproject.comment_added", work_package_id=work_package_id)
        return response.json()

    async def transition_status(
        self,
        work_package_id: str,
        status_id: int,
        lock_version: int,
    ) -> dict[str, Any]:
        payload = {
            "lockVersion": lock_version,
            "_links": {"status": {"href": f"/api/v3/statuses/{status_id}"}},
        }
        response = await self._client.request(
            "PATCH",
            f"/api/v3/work_packages/{work_package_id}",
            json=payload,
        )
        _logger.info(
            "openproject.status_transitioned",
            work_package_id=work_package_id,
            status_id=status_id,
        )
        return response.json()

    async def link_attachments(
        self,
        work_package_id: str,
        attachment_ids: list[int],
        lock_version: int,
    ) -> dict[str, Any]:
        payload = {
            "lockVersion": lock_version,
            "_links": {
                "attachments": [
                    {"href": f"/api/v3/attachments/{aid}"} for aid in attachment_ids
                ]
            },
        }
        response = await self._client.request(
            "PATCH",
            f"/api/v3/work_packages/{work_package_id}",
            json=payload,
        )
        return response.json()
