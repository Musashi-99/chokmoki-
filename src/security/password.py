"""Admin password hashing and verification."""

from __future__ import annotations

import secrets
from typing import Optional

from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plaintext: str) -> str:
    return _pwd_context.hash(plaintext)


def verify_password(plaintext: str, password_hash: Optional[str]) -> bool:
    normalized_hash = (password_hash or "").strip()
    if not normalized_hash:
        return False
    try:
        return _pwd_context.verify(plaintext, normalized_hash)
    except ValueError:
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
