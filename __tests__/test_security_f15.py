"""F-15 idempotency key tests."""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.security.idempotency import IdempotencyConflictError, IdempotencyService


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str, nx: bool = False, ex: int | None = None):
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    async def setex(self, key: str, ttl: int, value: str):
        self.store[key] = value

    async def delete(self, *keys: str):
        for key in keys:
            self.store.pop(key, None)


class TestIdempotencyService:
    @pytest.mark.asyncio
    async def test_store_and_replay(self, monkeypatch):
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")
        monkeypatch.setenv("IDEMPOTENCY_ENABLED", "true")

        fake = FakeRedis()
        service = IdempotencyService()
        key = service.normalize_key("order-abc-123")
        fingerprint = service.fingerprint(scope="order.create", payload={"userEmail": "a@test.com"})

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "src.security.idempotency.redis_client.get_client",
                AsyncMock(return_value=fake),
            )
            assert await service.begin(key, fingerprint) is None
            await service.store(key, fingerprint, status_code=200, body={"order_id": "o1"})
            replay = await service.begin(key, fingerprint)

        assert replay is not None
        assert replay.body["order_id"] == "o1"

    @pytest.mark.asyncio
    async def test_conflict_on_payload_mismatch(self, monkeypatch):
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")
        monkeypatch.setenv("IDEMPOTENCY_ENABLED", "true")

        fake = FakeRedis()
        service = IdempotencyService()
        key = service.normalize_key("shared-key")
        fp1 = service.fingerprint(scope="order.create", payload={"a": 1})
        fp2 = service.fingerprint(scope="order.create", payload={"a": 2})

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "src.security.idempotency.redis_client.get_client",
                AsyncMock(return_value=fake),
            )
            await service.store(key, fp1, status_code=200, body={"ok": True})
            with pytest.raises(IdempotencyConflictError):
                await service.begin(key, fp2)

    def test_fingerprint_is_stable(self):
        service = IdempotencyService()
        payload = {"b": 2, "a": 1}
        assert service.fingerprint(scope="x", payload=payload) == service.fingerprint(
            scope="x", payload={"a": 1, "b": 2}
        )
