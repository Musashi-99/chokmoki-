"""Redis-backed circuit breaker — state is visible across the `backend` and
`worker` processes (both call into Razorpay/Shiprocket/Telegram), unlike an
in-process counter which each process would track independently.

Classic counting breaker: N consecutive failures within a rolling window
trips it; while open, calls are short-circuited immediately (no network
call at all) for a cooldown period; after the cooldown, the next call is
let through as a trial — if it succeeds the breaker is effectively closed
again (the failure counter was already cleared), if it fails the counter
starts building toward the threshold again. This is a simpler variant than
a formal half-open state that limits trial concurrency, which isn't needed
here since call volume to any one dependency is low enough that a single
extra trial call during recovery is a non-issue.
"""
from __future__ import annotations

from typing import Awaitable, Callable, TypeVar

from src.database.redis_connection import redis_client

T = TypeVar("T")


class CircuitBreakerOpenError(Exception):
    def __init__(self, name: str):
        super().__init__(f"Circuit breaker '{name}' is open — short-circuiting call")
        self.name = name


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 5,
        failure_window_seconds: int = 60,
        cooldown_seconds: int = 30,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.failure_window_seconds = failure_window_seconds
        self.cooldown_seconds = cooldown_seconds
        self._open_key = f"breaker:{name}:open"
        self._failure_key = f"breaker:{name}:failures"
        self._notice_key = f"breaker:{name}:pending_reset_notice"

    async def is_open(self) -> bool:
        redis = await redis_client.get_client()
        return bool(await redis.exists(self._open_key))

    async def call(self, fn: Callable[[], Awaitable[T]]) -> T:
        if await self.is_open():
            raise CircuitBreakerOpenError(self.name)
        try:
            result = await fn()
        except Exception:
            await self._record_failure()
            raise
        else:
            await self._record_success()
            return result

    async def _record_failure(self) -> None:
        redis = await redis_client.get_client()
        count = await redis.incr(self._failure_key)
        if count == 1:
            await redis.expire(self._failure_key, self.failure_window_seconds)
        if count >= self.failure_threshold:
            # nx=True: only the caller that actually flips closed->open logs
            # the trip — every failure after that while still open is not a
            # new trip, just a confirming failure during the cooldown.
            tripped_now = await redis.set(self._open_key, "1", nx=True, ex=self.cooldown_seconds)
            await redis.delete(self._failure_key)
            if tripped_now:
                await redis.set(
                    self._notice_key, "1", ex=self.cooldown_seconds + 120
                )
                try:
                    from src.plugins.metrics import CIRCUIT_BREAKER_OPEN

                    CIRCUIT_BREAKER_OPEN.labels(name=self.name).set(1)
                except Exception:
                    pass
                try:
                    from src.services.system_log_service import SystemLogService

                    await SystemLogService().log(
                        component="circuit_breaker",
                        level="error",
                        message=(
                            f"Circuit breaker '{self.name}' tripped after "
                            f"{self.failure_threshold} failures — short-circuiting "
                            f"calls for {self.cooldown_seconds}s"
                        ),
                        context={
                            "name": self.name,
                            "failure_threshold": self.failure_threshold,
                            "cooldown_seconds": self.cooldown_seconds,
                        },
                    )
                except Exception:
                    pass

    async def _record_success(self) -> None:
        redis = await redis_client.get_client()
        await redis.delete(self._failure_key)
        # GETDEL is atomic — only the first success after a trip (while the
        # notice key still exists) logs the reset; later successes are just
        # normal, unremarkable operation.
        was_pending_reset = await redis.getdel(self._notice_key)
        if was_pending_reset:
            try:
                from src.plugins.metrics import CIRCUIT_BREAKER_OPEN

                CIRCUIT_BREAKER_OPEN.labels(name=self.name).set(0)
            except Exception:
                pass
            try:
                from src.services.system_log_service import SystemLogService

                await SystemLogService().log(
                    component="circuit_breaker",
                    level="info",
                    message=f"Circuit breaker '{self.name}' reset — calls succeeding again",
                    context={"name": self.name},
                )
            except Exception:
                pass
