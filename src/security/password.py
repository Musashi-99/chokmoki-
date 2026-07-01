"""Admin password hashing and verification."""

from __future__ import annotations

import secrets
from typing import Optional

import bcrypt

# bcrypt hashes at most the first 72 bytes of a password. bcrypt >= 5.0 raises
# ValueError on longer inputs instead of silently truncating, so we truncate
# explicitly to keep behaviour stable across versions. Cost factor 12 matches
# the previous passlib CryptContext default.
_BCRYPT_MAX_BYTES = 72
_BCRYPT_ROUNDS = 12


def _to_secret(plaintext: str) -> bytes:
    return (plaintext or "").encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(plaintext: str) -> str:
    hashed = bcrypt.hashpw(_to_secret(plaintext), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS))
    return hashed.decode("utf-8")


def verify_password(plaintext: str, password_hash: Optional[str]) -> bool:
    normalized_hash = (password_hash or "").strip()
    if not normalized_hash:
        return False
    try:
        return bcrypt.checkpw(_to_secret(plaintext), normalized_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def verify_admin_password(
    plaintext: str,
    *,
    password_hash: Optional[str],
    fallback_plaintext: Optional[str],
) -> bool:
    if password_hash:
        return verify_password(plaintext, password_hash)

    expected = fallback_plaintext or ""
    if not expected:
        return False
    return secrets.compare_digest(plaintext, expected)
