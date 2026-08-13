from __future__ import annotations

from typing import Dict, Optional

import httpx

from src.config import settings
from src.plugins.logger import logger
from src.resilience.circuit_breaker import CircuitBreaker
from src.resilience.guarded import call_guarded
from src.services.sms_template_service import SmsTemplateService
from src.services.user_service import normalize_phone

MSG91_BREAKER = CircuitBreaker(
    "msg91", failure_threshold=5, failure_window_seconds=60, cooldown_seconds=30
)


class Msg91Service:
    """Thin wrapper around MSG91's OTP API (login) and Flow API (lifecycle
    SMS). Mirrors TelegramService's shape: is_enabled() gate, calls wrapped
    through call_guarded, never raises — degrade (return False/None) on any
    failure rather than crash the caller.
    """

    def is_enabled(self) -> bool:
        return bool(settings.msg91_enabled and settings.msg91_auth_key)

    async def send_otp(self, phone: str) -> Optional[str]:
        """POST /otp — returns MSG91's request_id, or None on failure/disabled."""
        if not self.is_enabled():
            return None
        mobile = f"91{normalize_phone(phone)}"

        async def _send() -> Optional[str]:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{settings.msg91_base_url}/otp",
                    params={
                        "mobile": mobile,
                        "authkey": settings.msg91_auth_key,
                        "otp_length": settings.msg91_otp_length,
                        "otp_expiry": settings.msg91_otp_expiry_seconds // 60,
                    },
                    headers={"accept": "application/json"},
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("type") != "success":
                    raise RuntimeError(f"MSG91 send_otp failed: {data}")
                return data.get("request_id")

        try:
            return await call_guarded(
                dependency="msg91",
                fn=_send,
                breaker=MSG91_BREAKER,
                timeout_seconds=10.0,
                bulkhead_limit=10,
                retries=2,
                retryable_exceptions=(httpx.TransportError, httpx.TimeoutException),
            )
        except Exception as e:
            if logger:
                logger.error(f"MSG91 send_otp failed for {mobile}: {e}")
            return None

    async def verify_otp(self, phone: str, otp: str) -> bool:
        """GET /otp/verify — True only on MSG91's own explicit success."""
        if not self.is_enabled():
            return False
        mobile = f"91{normalize_phone(phone)}"

        async def _verify() -> bool:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{settings.msg91_base_url}/otp/verify",
                    params={"mobile": mobile, "otp": otp, "authkey": settings.msg91_auth_key},
                    headers={"accept": "application/json"},
                )
                data = resp.json()
                return data.get("type") == "success"

        try:
            return await call_guarded(
                dependency="msg91",
                fn=_verify,
                breaker=MSG91_BREAKER,
                timeout_seconds=10.0,
                bulkhead_limit=10,
                retries=1,
                retryable_exceptions=(httpx.TransportError, httpx.TimeoutException),
            )
        except Exception as e:
            if logger:
                logger.error(f"MSG91 verify_otp failed for {mobile}: {e}")
            return False

    async def send_template(self, phone: str, template_key: str, variables: Dict[str, str]) -> bool:
        """POST /flow — sends a DLT-registered template. No-ops (logs,
        returns False) if the template is missing/disabled/unconfigured,
        same "degrade, don't crash" rule as Telegram — a missed lifecycle
        SMS is never worth failing the order-status update that triggered it.
        """
        if not self.is_enabled():
            return False

        template = await SmsTemplateService().get_by_key(template_key)
        if not template or not template.enabled or not template.msg91_template_id:
            if logger:
                logger.info(f"MSG91 send_template skipped: '{template_key}' not configured/enabled")
            return False

        mobile = f"91{normalize_phone(phone)}"

        async def _send() -> bool:
            recipient = {"mobiles": mobile, **variables}
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{settings.msg91_base_url}/flow",
                    json={
                        "template_id": template.msg91_template_id,
                        "short_url": "0",
                        "recipients": [recipient],
                    },
                    headers={
                        "accept": "application/json",
                        "authkey": settings.msg91_auth_key,
                        "content-type": "application/json",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("type") != "success":
                    raise RuntimeError(f"MSG91 send_template failed: {data}")
                return True

        try:
            return await call_guarded(
                dependency="msg91",
                fn=_send,
                breaker=MSG91_BREAKER,
                timeout_seconds=10.0,
                bulkhead_limit=10,
                retries=2,
                retryable_exceptions=(httpx.TransportError, httpx.TimeoutException),
            )
        except Exception as e:
            if logger:
                logger.error(f"MSG91 send_template('{template_key}') failed for {mobile}: {e}")
            return False
