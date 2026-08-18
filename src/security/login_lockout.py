"""Adaptive admin login lockout backed by Redis."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional, Tuple

from src.config import settings
from src.database.redis_connection import redis_client
from src.security.exceptions import AccountLockedError


@dataclass(frozen=True)
class LockoutStatus:
    locked: bool
    retry_after_seconds: int = 0


class LoginLockoutService:
    LOCKOUT_PREFIX = "auth:lockout"
    FAILURE_PREFIX = "auth:fail"

    def __init__(self, kind: str = "auth") -> None:
        self.LOCKOUT_PREFIX = f"{kind}:lockout"
        self.FAILURE_PREFIX = f"{kind}:fail"

    @property
    def max_attempts(self) -> int:
        return settings.login_max_failed_attempts

    @property
    def lockout_seconds(self) -> int:
        return settings.login_lockout_seconds

    @property
    def failure_window_seconds(self) -> int:
        return settings.login_failure_window_seconds

    def _email_hash(self, email: str) -> str:
        return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:24]

    def _lockout_keys(self, ip: str, email: str) -> Tuple[str, str]:
        email_hash = self._email_hash(email)
        return (
            f"{self.LOCKOUT_PREFIX}:ip:{ip}",
            f"{self.LOCKOUT_PREFIX}:email:{email_hash}",
        )

    def _failure_keys(self, ip: str, email: str) -> Tuple[str, str]:
        email_hash = self._email_hash(email)
        return (
            f"{self.FAILURE_PREFIX}:ip:{ip}",
            f"{self.FAILURE_PREFIX}:email:{email_hash}",
        )

    async def get_status(self, ip: str, email: str) -> LockoutStatus:
        redis = await redis_client.get_client()
        lock_ip_key, lock_email_key = self._lockout_keys(ip, email)
        ttl_ip = await redis.ttl(lock_ip_key)
        ttl_email = await redis.ttl(lock_email_key)
        retry_after = max(ttl_ip, ttl_email, 0)
        if retry_after > 0:
            return LockoutStatus(locked=True, retry_after_seconds=retry_after)
        return LockoutStatus(locked=False)

    async def assert_not_locked(self, ip: str, email: str) -> None:
        status = await self.get_status(ip, email)
        if status.locked:
            raise AccountLockedError(status.retry_after_seconds)

    async def record_failure(self, ip: str, email: str) -> LockoutStatus:
        redis = await redis_client.get_client()
        fail_ip_key, fail_email_key = self._failure_keys(ip, email)
        lock_ip_key, lock_email_key = self._lockout_keys(ip, email)

        pipe = redis.pipeline()
        pipe.incr(fail_ip_key)
        pipe.expire(fail_ip_key, self.failure_window_seconds)
        pipe.incr(fail_email_key)
        pipe.expire(fail_email_key, self.failure_window_seconds)
        ip_count, _, email_count, _ = await pipe.execute()

        attempts = max(int(ip_count or 0), int(email_count or 0))
        if attempts >= self.max_attempts:
            pipe = redis.pipeline()
            pipe.setex(lock_ip_key, self.lockout_seconds, "1")
            pipe.setex(lock_email_key, self.lockout_seconds, "1")
            pipe.delete(fail_ip_key, fail_email_key)
            await pipe.execute()
            return LockoutStatus(locked=True, retry_after_seconds=self.lockout_seconds)

        return LockoutStatus(locked=False)

    async def record_success(self, ip: str, email: str) -> None:
        redis = await redis_client.get_client()
        fail_ip_key, fail_email_key = self._failure_keys(ip, email)
        lock_ip_key, lock_email_key = self._lockout_keys(ip, email)
        await redis.delete(fail_ip_key, fail_email_key, lock_ip_key, lock_email_key)
