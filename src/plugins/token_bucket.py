from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

from src.database.redis_connection import redis_client
from src.plugins.rate_limit_config import RateLimitBucket, read_lua_script


@dataclass(frozen=True)
class TokenBucketResult:
    allowed: bool
    retry_after_ms: int


class TokenBucketLimiter:
    def __init__(self) -> None:
        self._script_sha: Optional[str] = None
        self._script_source = read_lua_script()

    async def _ensure_script(self, redis) -> str:
        if self._script_sha:
            return self._script_sha
        self._script_sha = await redis.script_load(self._script_source)
        return self._script_sha

    async def consume(self, redis_key: str, bucket: RateLimitBucket, cost: int = 1) -> TokenBucketResult:
        redis = await redis_client.get_client()
        sha = await self._ensure_script(redis)
        now_ms = int(time.time() * 1000)
        ttl_ms = max(bucket.window_seconds * 1000 * 2, 60_000)

        try:
            result = await redis.evalsha(
                sha,
                1,
                redis_key,
                bucket.capacity,
                bucket.refill_per_ms,
                now_ms,
                cost,
                ttl_ms,
            )
        except Exception:
            result = await redis.eval(
                self._script_source,
                1,
                redis_key,
                bucket.capacity,
                bucket.refill_per_ms,
                now_ms,
                cost,
                ttl_ms,
            )

        allowed = int(result[0]) == 1
        retry_after_ms = int(result[1])
        return TokenBucketResult(allowed=allowed, retry_after_ms=retry_after_ms)

    async def check_all(
        self, checks: List[Tuple[str, RateLimitBucket]]
    ) -> TokenBucketResult:
        for redis_key, bucket in checks:
            result = await self.consume(redis_key, bucket)
            if not result.allowed:
                return result
        return TokenBucketResult(allowed=True, retry_after_ms=0)
