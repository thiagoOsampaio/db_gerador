"""CredentialVault encrypt/decrypt roundtrip + TTL behavior."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import SecretStr

from backend.config import get_settings
from backend.domain.enums import DatabaseType
from backend.domain.exceptions import (
    CredentialDecryptionError,
    CredentialExpiredError,
)
from backend.domain.models.database import DatabaseConnection
from backend.security.credentials import CredentialVault


def _make_connection() -> DatabaseConnection:
    return DatabaseConnection(
        database_type=DatabaseType.POSTGRESQL,
        host="db.example.com",
        port=5432,
        database_name="customer_app",
        username="customer",
        password=SecretStr("c0mpl3x-p@ss!"),
    )


def test_encrypt_decrypt_roundtrip() -> None:
    vault = CredentialVault(get_settings())
    original = _make_connection()
    encrypted = vault.encrypt(original)
    assert b"c0mpl3x-p@ss" not in encrypted.ciphertext

    decrypted = vault.decrypt(encrypted.ciphertext, encrypted.expires_at)
    assert decrypted.password.get_secret_value() == "c0mpl3x-p@ss!"
    assert decrypted.host == "db.example.com"
    assert decrypted.database_type is DatabaseType.POSTGRESQL


def test_expired_credential_rejected() -> None:
    vault = CredentialVault(get_settings())
    encrypted = vault.encrypt(_make_connection())
    past = datetime.now(tz=timezone.utc) - timedelta(seconds=1)
    with pytest.raises(CredentialExpiredError):
        vault.decrypt(encrypted.ciphertext, past)


def test_tampered_ciphertext_rejected() -> None:
    vault = CredentialVault(get_settings())
    encrypted = vault.encrypt(_make_connection())
    tampered = encrypted.ciphertext[:-2] + b"00"
    with pytest.raises(CredentialDecryptionError):
        vault.decrypt(tampered, encrypted.expires_at)


def test_safe_repr_redacts_password() -> None:
    repr_str = _make_connection().safe_repr()
    assert "c0mpl3x" not in repr_str
    assert "***" in repr_str
