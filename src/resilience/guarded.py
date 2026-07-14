"""Single composition point for the four resilience primitives — so call
sites reach for one function instead of remembering to nest bulkhead(),
breaker.call(), retry_async(), and with_timeout() correctly every time.

Order (outermost to innermost): bulkhead -> breaker -> retry -> timeout ->
call. The breaker check happens before spending a retry budget or blocking
on a real network call — if it's open, callers fail immediately. Retry
wraps each individual timeout-guarded attempt, so a slow-but-eventually-
successful call still gets its own fresh timeout on every attempt.
"""
from __future__ import annotations

import time
from typing import Awaitable, Callable, Tuple, Type, TypeVar

from src.plugins.metrics import DEPENDENCY_CALL_LATENCY_MS, DEPENDENCY_CALL_TOTAL
from src.resilience.bulkhead import with_bulkhead
from src.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from src.resilience.retry import retry_async
from src.resilience.timeout import DependencyTimeoutError, with_timeout

T = TypeVar("T")


async def call_guarded(
    *,
    dependency: str,
    fn: Callable[[], Awaitable[T]],
    breaker: CircuitBreaker,
    timeout_seconds: float,
    bulkhead_limit: int,
    retries: int = 2,
    retryable_exceptions: Tuple[Type[BaseException], ...] = (Exception,),
) -> T:
    # DependencyTimeoutError is always retryable regardless of what the
    # caller passed — a timeout is the textbook transient failure, and
    # forgetting to include it at every call site would be an easy mistake.
    effective_retryable = tuple(set(retryable_exceptions) | {DependencyTimeoutError})

    async def attempt() -> T:
        return await with_timeout(fn(), seconds=timeout_seconds, dependency=dependency)

    async def retried() -> T:
        return await retry_async(
            attempt, retries=retries, retryable_exceptions=effective_retryable
        )

    async def breaker_gated() -> T:
        return await breaker.call(retried)

    # Metrics recorded once here — the single composition point — rather
    # than at every Razorpay/Shiprocket/Telegram call site, so every guarded
    # call is automatically observed with no per-service instrumentation.
    start = time.monotonic()
    try:
        result = await with_bulkhead(dependency, bulkhead_limit, breaker_gated)
        DEPENDENCY_CALL_TOTAL.labels(dependency=dependency, outcome="success").inc()
        return result
    except CircuitBreakerOpenError:
        DEPENDENCY_CALL_TOTAL.labels(dependency=dependency, outcome="breaker_open").inc()
        raise
    except DependencyTimeoutError:
        DEPENDENCY_CALL_TOTAL.labels(dependency=dependency, outcome="timeout").inc()
        raise
    except Exception:
        DEPENDENCY_CALL_TOTAL.labels(dependency=dependency, outcome="failure").inc()
        raise
    finally:
        DEPENDENCY_CALL_LATENCY_MS.labels(dependency=dependency).observe(
            (time.monotonic() - start) * 1000
        )
