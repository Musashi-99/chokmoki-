from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class AlertEvent:
    type: str
    payload: Dict[str, Any]


class AlertHandler(ABC):
    """One link in a Chain of Responsibility.

    Each concrete handler decides whether it owns a given event
    (`_can_handle`) and, if so, turns it into a notification (`_process`).
    If it doesn't own the event, `handle()` passes it to the next link.
    Build a chain with `set_next()` and always terminate it with a handler
    that unconditionally matches (see FallbackHandler) so every event is
    accounted for — nothing silently falls off the end of the chain.
    """

    def __init__(self) -> None:
        self._next: Optional["AlertHandler"] = None

    def set_next(self, handler: "AlertHandler") -> "AlertHandler":
        self._next = handler
        return handler

    async def handle(self, event: AlertEvent) -> bool:
        if await self._can_handle(event):
            return await self._process(event)
        if self._next is not None:
            return await self._next.handle(event)
        return False

    @abstractmethod
    async def _can_handle(self, event: AlertEvent) -> bool: ...

    @abstractmethod
    async def _process(self, event: AlertEvent) -> bool: ...
