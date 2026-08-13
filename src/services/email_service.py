from __future__ import annotations

import asyncio
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from src.config import settings
from src.plugins.logger import logger
from src.resilience.circuit_breaker import CircuitBreaker
from src.resilience.guarded import call_guarded

EMAIL_BREAKER = CircuitBreaker(
    "brevo_smtp", failure_threshold=5, failure_window_seconds=60, cooldown_seconds=30
)


class EmailService:
    """Thin wrapper around Brevo's SMTP relay. Mirrors Msg91Service's shape:
    is_enabled() gate, calls wrapped through call_guarded, never raises —
    degrade (return False) on any failure rather than crash the caller, so a
    dead SMTP relay never blocks checkout/login.
    """

    def is_enabled(self) -> bool:
        return settings.email_enabled

    def _send_sync(self, to: str, subject: str, html_body: str) -> None:
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = formataddr((settings.invoice_brand_name, settings.smtp_from))
        message["To"] = to
        message.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as client:
            client.starttls()
            client.login(settings.smtp_username, settings.smtp_password)
            client.sendmail(settings.smtp_from, [to], message.as_string())

    async def send(self, to: str, subject: str, html_body: str) -> bool:
        if not self.is_enabled():
            if logger:
                logger.warning("Email not sent — SMTP is not configured (to=%s)", to)
            return False

        async def _send() -> None:
            await asyncio.to_thread(self._send_sync, to, subject, html_body)

        try:
            await call_guarded(
                dependency="brevo_smtp",
                fn=_send,
                breaker=EMAIL_BREAKER,
                timeout_seconds=15.0,
                bulkhead_limit=10,
                retries=1,
            )
            return True
        except Exception as e:
            if logger:
                logger.error(f"Failed to send email to {to}: {e}")
            return False
