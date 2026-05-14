"""Structlog configuration.

Logs are JSON by default and pass through a sanitizer processor that
redacts any secret-shaped values before serialization.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from structlog.types import EventDict, Processor

from backend.config import Settings
from backend.security.sanitizer import sanitize_mapping, sanitize_string


def _sanitize_processor(_: Any, __: str, event_dict: EventDict) -> EventDict:
    """Remove secrets from log payloads."""
    if "event" in event_dict and isinstance(event_dict["event"], str):
        event_dict["event"] = sanitize_string(event_dict["event"])
    return sanitize_mapping(event_dict)  # type: ignore[return-value]


def configure_logging(settings: Settings) -> None:
    """Configure structlog + stdlib logging."""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        timestamper,
        _sanitize_processor,
    ]

    renderer: Processor = (
        structlog.processors.JSONRenderer()
        if settings.LOG_JSON
        else structlog.dev.ConsoleRenderer(colors=False)
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]
