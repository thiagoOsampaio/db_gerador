"""Customer-database credential vault (Fernet symmetric encryption).

Encrypted blobs are persisted in PostgreSQL with a TTL. Plaintext
credentials live only in process memory long enough to perform schema
introspection, then are discarded. Agents never receive credentials.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr

from backend.config import Settings
from backend.domain.enums import DatabaseType
from backend.domain.exceptions import (
    CredentialDecryptionError,
    CredentialExpiredError,
)
from backend.domain.models.database import DatabaseConnection


@dataclass(frozen=True)
class EncryptedCredential:
    """An encrypted credential blob plus expiration metadata."""

    ciphertext: bytes
    expires_at: datetime


class CredentialVault:
    """Encrypt / decrypt customer ``DatabaseConnection`` payloads.

    Secrets are serialized as JSON, Fernet-encrypted, then handed back to
    the caller for persistence. The vault itself is stateless.
    """

    def __init__(self, settings: Settings) -> None:
        key = settings.CREDENTIAL_ENCRYPTION_KEY.get_secret_value().encode()
        self._fernet = Fernet(key)
        self._ttl = timedelta(hours=settings.CREDENTIAL_TTL_HOURS)

    def encrypt(self, connection: DatabaseConnection) -> EncryptedCredential:
        payload = {
            "database_type": connection.database_type.value,
            "host": connection.host,
            "port": connection.port,
            "database_name": connection.database_name,
            "username": connection.username,
            "password": connection.password.get_secret_value(),
        }
        ciphertext = self._fernet.encrypt(json.dumps(payload).encode())
        expires_at = datetime.now(tz=timezone.utc) + self._ttl
        return EncryptedCredential(ciphertext=ciphertext, expires_at=expires_at)

    def decrypt(
        self,
        ciphertext: bytes,
        expires_at: datetime | None = None,
    ) -> DatabaseConnection:
        if expires_at is not None and datetime.now(tz=timezone.utc) > expires_at:
            raise CredentialExpiredError("Stored credential has expired")
        try:
            raw = self._fernet.decrypt(ciphertext)
        except InvalidToken as exc:
            raise CredentialDecryptionError("Invalid encryption token") from exc
        try:
            data = json.loads(raw.decode())
            return DatabaseConnection(
                database_type=DatabaseType(data["database_type"]),
                host=data["host"],
                port=data["port"],
                database_name=data["database_name"],
                username=data["username"],
                password=SecretStr(data["password"]),
            )
        except (KeyError, ValueError) as exc:
            raise CredentialDecryptionError("Malformed credential payload") from exc

    # ------------------------------------------------------------------
    # Token vault (used for the per-user OpenProject token)
    # ------------------------------------------------------------------
    def encrypt_token(self, token: str) -> bytes:
        """Encrypt an arbitrary secret string (e.g. an API token)."""
        return self._fernet.encrypt(token.encode())

    def decrypt_token(self, ciphertext: bytes) -> SecretStr:
        """Decrypt a token previously produced by :meth:`encrypt_token`."""
        try:
            raw = self._fernet.decrypt(ciphertext)
        except InvalidToken as exc:
            raise CredentialDecryptionError("Invalid token ciphertext") from exc
        return SecretStr(raw.decode())
