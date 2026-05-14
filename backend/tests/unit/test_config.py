"""Settings load from env without leaking secrets."""

from __future__ import annotations

from backend.config import get_settings


def test_settings_dsn_includes_password_but_repr_does_not() -> None:
    settings = get_settings()
    # DSN must contain the password for SQLAlchemy.
    assert settings.POSTGRES_PASSWORD.get_secret_value() in settings.postgres_dsn_async
    # str(settings) must NOT contain any secret in plaintext.
    rendered = repr(settings)
    assert settings.POSTGRES_PASSWORD.get_secret_value() not in rendered
    assert settings.GEMINI_API_KEY.get_secret_value() not in rendered
    assert settings.CREDENTIAL_ENCRYPTION_KEY.get_secret_value() not in rendered


def test_openproject_url_strips_trailing_slash() -> None:
    settings = get_settings()
    assert not settings.OPENPROJECT_API_URL.endswith("/")
