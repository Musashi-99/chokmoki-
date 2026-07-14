"""Per-dependency concurrency cap, in-process.

Deliberately NOT cross-process/Redis-backed (unlike circuit_breaker.py) —
the problem this solves is "one slow dependency shouldn't starve *this
process's* asyncio.to_thread executor for unrelated work," which is purely a
per-process concern. Each of `backend` and `worker` gets its own independent
cap for the same dependency name, which is correct: they're different
processes with their own thread pools.
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Dict, TypeVar

T = TypeVar("T")

_semaphores: Dict[str, asyncio.Semaphore] = {}


def _get_semaphore(name: str, limit: int) -> asyncio.Semaphore:
    sem = _semaphores.get(name)
    if sem is None:
        sem = asyncio.Semaphore(limit)
        _semaphores[name] = sem
    return sem


async def with_bulkhead(name: str, limit: int, fn: Callable[[], Awaitable[T]]) -> T:
    """Run `fn()` only once fewer than `limit` calls to dependency `name` are
    already in flight in this process — extra callers wait their turn rather
    than piling on top of an already-slow dependency.
    """
    sem = _get_semaphore(name, limit)
    async with sem:
        return await fn()
