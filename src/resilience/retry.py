"""Exponential backoff with jitter for transient outbound-call failures.

Only wrap TRANSIENT errors here (timeouts, connection errors, 429/5xx) —
never a 4xx that means "this specific request is wrong" (bad amount, invalid
signature, etc). Retrying those just delays a real error and can duplicate
side effects if the request actually succeeded server-side before the
response was lost.
"""
from __future__ import annotations

import asyncio
import random
from typing import Awaitable, Callable, Optional, Tuple, Type, TypeVar

T = TypeVar("T")


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    retries: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    jitter: float = 0.3,
    retryable_exceptions: Tuple[Type[BaseException], ...] = (Exception,),
    on_retry: Optional[Callable[[int, BaseException], None]] = None,
) -> T:
    """Call `fn()` (a zero-arg callable returning an awaitable — a fresh one
    each attempt, since a coroutine object can't be awaited twice), retrying
    up to `retries` times on `retryable_exceptions` with exponential backoff
    (base_delay * 2^attempt, capped at max_delay) plus up to `jitter` extra
    randomized delay — jitter spreads out retries from concurrent callers so
    they don't all hammer the dependency again at exactly the same moment.

    `on_retry(attempt, exc)` is a best-effort hook (e.g. for logging) — an
    exception in it is swallowed, since a broken retry-logger must never
    break the actual retry logic.
    """
    attempt = 0
    while True:
        try:
            return await fn()
        except retryable_exceptions as e:
            attempt += 1
            if attempt > retries:
                raise
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            delay += random.uniform(0, jitter * delay)
            if on_retry is not None:
                try:
                    on_retry(attempt, e)
                except Exception:
                    pass
            await asyncio.sleep(delay)
