"""Low-level async HTTP client for OpenProject v3.

The API token is supplied per-request by the calling user. The backend
only owns ``OPENPROJECT_API_URL``; tokens never come from environment
variables. The token never leaves this module's HTTP layer.
"""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import SecretStr
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from backend.domain.exceptions import OpenProjectError
from backend.observability.logging import get_logger

_logger = get_logger(__name__)


class OpenProjectClient:
    """Thin async wrapper over OpenProject's REST API v3."""

    def __init__(
        self,
        *,
        api_url: str,
        token: SecretStr,
        timeout: int = 30,
    ) -> None:
        # OpenProject uses basic auth with "apikey" as the username.
        self._client = httpx.AsyncClient(
            base_url=api_url.rstrip("/"),
            auth=httpx.BasicAuth("apikey", token.get_secret_value()),
            timeout=timeout,
            headers={"Accept": "application/json"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> OpenProjectClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()

    # ------------------------------------------------------------------
    # Generic request helpers with retry
    # ------------------------------------------------------------------
    async def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=2, min=2, max=8),
            retry=retry_if_exception_type(
                (httpx.TransportError, httpx.HTTPStatusError)
            ),
            reraise=True,
        ):
            with attempt:
                response = await self._client.request(
                    method,
                    path,
                    json=json,
                    content=content,
                    headers=headers,
                    params=params,
                )
                if response.status_code >= 500:
                    response.raise_for_status()
                if response.status_code >= 400:
                    _logger.warning(
                        "openproject.client_error",
                        method=method,
                        path=path,
                        status=response.status_code,
                    )
                    raise OpenProjectError(
                        f"OpenProject {method} {path} returned {response.status_code}",
                        status_code=response.status_code,
                    )
                return response
        raise RuntimeError("unreachable")  # pragma: no cover
