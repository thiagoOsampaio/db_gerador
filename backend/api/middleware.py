"""FastAPI middleware: request id + structured access log."""

from __future__ import annotations

import time
from uuid import uuid4

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Bind a request id to the structlog context for every request."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            path=request.url.path,
            method=request.method,
        )
        start = time.perf_counter()
        try:
            response: Response = await call_next(request)
        except Exception:
            structlog.get_logger("http").exception("http.request.error")
            raise
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            structlog.get_logger("http").info(
                "http.request",
                duration_ms=duration_ms,
            )
        response.headers["X-Request-ID"] = request_id
        return response
