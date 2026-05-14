"""Sanitizer must redact passwords, tokens, and connection strings."""

from __future__ import annotations

from backend.security.sanitizer import (
    sanitize_mapping,
    sanitize_string,
)


def test_sanitize_connection_string() -> None:
    s = "Connecting to postgresql://alice:s3cret@db.example.com:5432/app"
    out = sanitize_string(s)
    assert "s3cret" not in out
    assert "alice" in out
    assert "***" in out


def test_sanitize_password_key_value() -> None:
    s = 'config: password="topSecret!" host=db'
    out = sanitize_string(s)
    assert "topSecret!" not in out
    assert "REDACTED" in out


def test_sanitize_mapping_recursive() -> None:
    data = {
        "user": "bob",
        "Password": "supersecret",
        "nested": {"api_key": "k-123", "ok": "value"},
        "tokens": ["bearer xyz", "plain"],
    }
    out = sanitize_mapping(data)
    assert out["user"] == "bob"
    assert "supersecret" not in str(out)
    assert "k-123" not in str(out)


def test_sanitize_dsn_with_special_chars() -> None:
    s = "mysql://u:p%40ss@host:3306/db"
    out = sanitize_string(s)
    assert "p%40ss" not in out
