from telegram import Bot
from telegram.error import TelegramError

from src.config import settings
from src.plugins.logger import logger


class TelegramService:
    """Thin wrapper around the Telegram Bot API. Real-time alert formatting
    and dispatch logic lives in src/alerts/ (Chain of Responsibility over a
    Redis Streams consumer) — this class only knows how to check whether
    Telegram is configured and send a single message.
    """

    def is_enabled(self) -> bool:
        if not settings.telegram_enabled:
            return False
        if not settings.telegram_bot_token or not settings.telegram_chat_id:
            return False
        return True

    async def send_message(self, text: str) -> bool:
        """Send message to Telegram using python-telegram-bot SDK"""
        if not self.is_enabled():
            return False

        try:
            bot = Bot(token=settings.telegram_bot_token)
            await bot.send_message(
                chat_id=settings.telegram_chat_id,
                text=text,
                parse_mode="Markdown",
                disable_web_page_preview=False,
            )
            return True
        except TelegramError as e:
            if logger:
                logger.error(f"Telegram API error: {e}")
            return False
        except Exception as e:
            if logger:
                logger.error(f"Failed to send Telegram message: {e}")
            return False
