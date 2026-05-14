"""Sanitization helpers — strip secrets from any string before logging.

These utilities are conservative: when in doubt, redact. They are used
across logging processors, exception handlers, and any place that may
materialize secret values into observable strings.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_REDACTED = "***REDACTED***"

# Order matters: more-specific patterns first.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Connection strings with embedded credentials.
    re.compile(r"(?P<scheme>\w+://)(?P<user>[^:@/\s]+):(?P<pwd>[^@/\s]+)@"),
    # key=value style secrets.
    re.compile(
        r"(?P<key>(password|passwd|pwd|secret|api[_-]?key|token|authorization|bearer))"
        r"\s*[:=]\s*['\"]?(?P<value>[^'\"\s,;]+)['\"]?",
        re.IGNORECASE,
    ),
)

_SENSITIVE_KEY_FRAGMENTS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "secret",
        "api_key",
        "apikey",
        "token",
        "authorization",
        "bearer",
        "credential",
        "private_key",
        "encryption_key",
    }
)


def _is_sensitive_key(key: str) -> bool:
    k = key.lower()
    return any(fragment in k for fragment in _SENSITIVE_KEY_FRAGMENTS)


def sanitize_string(value: str) -> str:
    """Redact secrets inline within a free-form string."""
    sanitized = value
    sanitized = _SECRET_PATTERNS[0].sub(lambda m: f"{m.group('scheme')}{m.group('user')}:***@", sanitized)
    sanitized = _SECRET_PATTERNS[1].sub(lambda m: f"{m.group('key')}={_REDACTED}", sanitized)
    return sanitized


def sanitize_mapping(data: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively redact sensitive values in dict-like structures."""
    return {k: _sanitize_value(k, v) for k, v in data.items()}


def _sanitize_value(key: str, value: Any) -> Any:
    if _is_sensitive_key(key):
        return _REDACTED
    if isinstance(value, str):
        return sanitize_string(value)
    if isinstance(value, Mapping):
        return sanitize_mapping(value)
    if isinstance(value, list | tuple):
        return [_sanitize_value(key, item) for item in value]
    return value


def sanitize(obj: Any) -> Any:
    """Polymorphic entry point used by logging processors."""
    if isinstance(obj, str):
        return sanitize_string(obj)
    if isinstance(obj, Mapping):
        return sanitize_mapping(obj)
    return obj
