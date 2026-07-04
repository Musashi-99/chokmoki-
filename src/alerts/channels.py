from __future__ import annotations

from abc import ABC, abstractmethod

from src.services.telegram_service import TelegramService


class NotificationChannel(ABC):
    """Where a formatted alert message actually gets delivered. Handlers
    depend on this, not on Telegram directly — adding Slack/email later is a
    new channel class, with no changes to src/alerts/handlers.py.
    """

    @abstractmethod
    async def send(self, text: str) -> bool: ...


class TelegramChannel(NotificationChannel):
    def __init__(self) -> None:
        self._telegram = TelegramService()

    def is_enabled(self) -> bool:
        return self._telegram.is_enabled()

    async def send(self, text: str) -> bool:
        if not self._telegram.is_enabled():
            return False
        return await self._telegram.send_message(text)
