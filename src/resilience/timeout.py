"""Thin timeout wrapper for coroutines wrapping blocking SDK calls.

Why this exists: razorpay.Client (used via asyncio.to_thread) has no
configurable timeout at all — a hung Razorpay socket would otherwise block
that thread indefinitely. httpx-based clients (Shiprocket) already have
their own timeout, but wrapping them here too keeps every outbound call
consistent and gives one place to tune/observe timeout behavior.
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, TypeVar

T = TypeVar("T")


class DependencyTimeoutError(Exception):
    """Raised when a wrapped call exceeds its allotted time. Distinct from
    asyncio.TimeoutError so callers can catch it without also catching
    unrelated timeouts (e.g. a Mongo operation's own timeout) that happen to
    propagate through the same code path.
    """

    def __init__(self, dependency: str, seconds: float):
        super().__init__(f"{dependency} call exceeded {seconds}s timeout")
        self.dependency = dependency
        self.seconds = seconds


async def with_timeout(coro: Awaitable[T], *, seconds: float, dependency: str) -> T:
    """Await `coro`, raising DependencyTimeoutError if it takes longer than
    `seconds`. `dependency` is just a label for the error message/logs —
    this has no side effects on the underlying call beyond cancelling it.
    """
    try:
        return await asyncio.wait_for(coro, timeout=seconds)
    except asyncio.TimeoutError as e:
        raise DependencyTimeoutError(dependency, seconds) from e
