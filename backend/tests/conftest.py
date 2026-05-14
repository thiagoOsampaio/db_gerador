"""Shared pytest fixtures and bootstrap.

Sets dummy environment variables required by :class:`Settings` so that
unit tests can import the configuration module without external infra.
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet

os.environ.setdefault("GEMINI_API_KEY", "fake-gemini-key-xyz")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_DB", "unit_db")
os.environ.setdefault("POSTGRES_USER", "unit_user")
os.environ.setdefault("POSTGRES_PASSWORD", "unitPwdNotInRepr_123")
os.environ.setdefault("OPENPROJECT_API_URL", "https://op.example.com")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("LOG_JSON", "false")
