"""Typed domain exceptions used across services and agents.

All exceptions intentionally exclude sensitive payloads from their string
representation. Callers must sanitize any contextual data before raising.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for domain-level errors."""


class ConfigurationError(DomainError):
    """Misconfigured environment / settings."""


class CredentialDecryptionError(DomainError):
    """Failed to decrypt a stored credential blob."""


class CredentialExpiredError(DomainError):
    """A stored credential has exceeded its TTL."""


class DatabaseConnectionError(DomainError):
    """Cannot connect to a customer database for introspection."""


class SchemaIntrospectionError(DomainError):
    """Failed to introspect schema from a customer database."""


class SchemaValidationError(DomainError):
    """Extracted or provided schema failed validation."""


class AgentExecutionError(DomainError):
    """A specialized agent failed to produce a structured output."""

    def __init__(self, agent_name: str, message: str) -> None:
        super().__init__(f"[{agent_name}] {message}")
        self.agent_name = agent_name


class WorkflowError(DomainError):
    """Workflow orchestration error."""


class SqlGenerationError(DomainError):
    """Deterministic SQL generation failure."""


class DiagramGenerationError(DomainError):
    """Deterministic Mermaid generation failure."""


class OpenProjectError(DomainError):
    """OpenProject REST API error."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class AnalysisNotFoundError(DomainError):
    """No analysis session matches the given id."""


class InvalidApprovalStateError(DomainError):
    """Approval/rejection requested while not awaiting approval."""
