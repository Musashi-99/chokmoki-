"""Redis-backed idempotency for order and payment mutations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from src.config import settings
from src.database.redis_connection import redis_client


class IdempotencyConflictError(Exception):
    """Raised when the same key is reused with a different request body."""


@dataclass(frozen=True)
class IdempotencyRecord:
    fingerprint: str
    status_code: int
    body: Dict[str, Any]


class IdempotencyService:
    PREFIX = "idempotency:"
    LOCK_SUFFIX = ":lock"

    @staticmethod
    def fingerprint(*, scope: str, payload: Dict[str, Any]) -> str:
        normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        digest = hashlib.sha256(f"{scope}:{normalized}".encode("utf-8")).hexdigest()
        return digest

    @staticmethod
    def normalize_key(key: str) -> str:
        value = (key or "").strip()
        if not value or len(value) > 128:
            raise ValueError("Idempotency-Key must be 1-128 characters")
        return value

    async def begin(self, key: str, fingerprint: str) -> Optional[IdempotencyRecord]:
        if not settings.idempotency_enabled:
            return None

        redis = await redis_client.get_client()
        storage_key = f"{self.PREFIX}{key}"
        existing = await redis.get(storage_key)
        if existing:
            data = json.loads(existing)
            if data.get("fingerprint") != fingerprint:
                raise IdempotencyConflictError("Idempotency-Key reused with different payload")
            return IdempotencyRecord(
                fingerprint=data["fingerprint"],
                status_code=int(data["status_code"]),
                body=data["body"],
            )

        lock_key = f"{storage_key}{self.LOCK_SUFFIX}"
        acquired = await redis.set(lock_key, fingerprint, nx=True, ex=60)
        if not acquired:
            existing = await redis.get(storage_key)
            if existing:
                data = json.loads(existing)
                if data.get("fingerprint") != fingerprint:
                    raise IdempotencyConflictError(
                        "Idempotency-Key reused with different payload"
                    )
                return IdempotencyRecord(
                    fingerprint=data["fingerprint"],
                    status_code=int(data["status_code"]),
                    body=data["body"],
                )
        return None

    async def store(
        self, key: str, fingerprint: str, *, status_code: int, body: Dict[str, Any]
    ) -> None:
        if not settings.idempotency_enabled:
            return

        redis = await redis_client.get_client()
        storage_key = f"{self.PREFIX}{key}"
        payload = {
            "fingerprint": fingerprint,
            "status_code": status_code,
            "body": body,
        }
        await redis.setex(
            storage_key,
            settings.idempotency_ttl_seconds,
            json.dumps(payload, default=str),
        )
        await redis.delete(f"{storage_key}{self.LOCK_SUFFIX}")

    async def release_lock(self, key: str) -> None:
        if not settings.idempotency_enabled:
            return
        redis = await redis_client.get_client()
        await redis.delete(f"{self.PREFIX}{key}{self.LOCK_SUFFIX}")
