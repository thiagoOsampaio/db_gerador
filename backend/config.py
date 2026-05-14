from __future__ import annotations

from functools import lru_cache
from urllib.parse import quote

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Backend service settings.

    Categories:
        - Gemini: sole LLM provider, key never exposed to users/agents.
        - PostgreSQL: backend infrastructure database (not customer DBs).
        - OpenProject: backend-owned credentials. Users supply only task_id.
        - Encryption: Fernet key for customer credential at-rest encryption.
        - Observability: structured logging configuration.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Gemini (sole LLM provider)
    # ------------------------------------------------------------------
    GEMINI_API_KEY: SecretStr
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_TEMPERATURE: float = 0.0
    GEMINI_MAX_RETRIES: int = 3
    GEMINI_REQUEST_TIMEOUT: int = 300

    # ------------------------------------------------------------------
    # PostgreSQL (backend infrastructure)
    # ------------------------------------------------------------------
    POSTGRES_HOST: str
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: SecretStr
    POSTGRES_SCHEMA: str = "analisador_de_banco"
    POSTGRES_POOL_SIZE: int = 10
    POSTGRES_MAX_OVERFLOW: int = 20

    # ------------------------------------------------------------------
    # OpenProject (user-supplied credentials)
    # The token is provided per-request by the calling user; this URL
    # is the only backend-owned piece of OpenProject configuration.
    # ------------------------------------------------------------------
    OPENPROJECT_API_URL: str
    OPENPROJECT_TIMEOUT: int = 30

    # ------------------------------------------------------------------
    # Encryption (customer DB credentials at rest)
    # ------------------------------------------------------------------
    CREDENTIAL_ENCRYPTION_KEY: SecretStr
    CREDENTIAL_TTL_HOURS: int = 24

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = True

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------
    API_HOST: str = "0.0.0.0"  # noqa: S104 - binds inside container
    API_PORT: int = 8000
    API_CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["*"])

    @field_validator("OPENPROJECT_API_URL")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------
    @property
    def postgres_dsn_async(self) -> str:
        """SQLAlchemy async DSN for application persistence.

        ``POSTGRES_SCHEMA`` is applied separately at engine-build time
        via asyncpg's ``server_settings`` connect arg (see
        :class:`backend.persistence.database.Database`).
        """
        pwd = quote(self.POSTGRES_PASSWORD.get_secret_value(), safe="")
        user = quote(self.POSTGRES_USER, safe="")
        return (
            f"postgresql+asyncpg://{user}:{pwd}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def postgres_dsn_sync(self) -> str:
        """Synchronous SQLAlchemy DSN (used by Alembic, via psycopg v3)."""
        pwd = quote(self.POSTGRES_PASSWORD.get_secret_value(), safe="")
        user = quote(self.POSTGRES_USER, safe="")
        opts = quote(f"-csearch_path={self.POSTGRES_SCHEMA}", safe="")
        return (
            f"postgresql+psycopg://{user}:{pwd}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            f"?options={opts}"
        )

    @property
    def postgres_dsn_psycopg(self) -> str:
        """Raw psycopg DSN (used by the LangGraph checkpointer)."""
        pwd = quote(self.POSTGRES_PASSWORD.get_secret_value(), safe="")
        user = quote(self.POSTGRES_USER, safe="")
        opts = quote(f"-csearch_path={self.POSTGRES_SCHEMA}", safe="")
        return (
            f"postgresql://{user}:{pwd}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            f"?options={opts}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor. Raises on missing required env vars."""
    return Settings()  # type: ignore[call-arg]
