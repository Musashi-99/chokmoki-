from __future__ import annotations

import hashlib
import secrets
from abc import ABC, abstractmethod

from src.config import settings
from src.database.redis_connection import redis_client
from src.services.email_service import EmailService
from src.services.email_templates import render_otp_email
from src.services.msg91_service import Msg91Service


class OtpChannel(ABC):
    """Adapter interface so CustomerAuthService doesn't care whether an OTP
    travels over SMS (MSG91) or email (Brevo) — both channels seen by their
    common send_otp/verify_otp shape.
    """

    @abstractmethod
    async def send_otp(self, identifier: str) -> bool: ...

    @abstractmethod
    async def verify_otp(self, identifier: str, otp: str) -> bool: ...


class Msg91OtpChannel(OtpChannel):
    """Delegates to Msg91Service unchanged — MSG91 generates, stores, and
    verifies the OTP on its own side; we only relay request_id/pass-fail.
    """

    def __init__(self) -> None:
        self._msg91 = Msg91Service()

    async def send_otp(self, identifier: str) -> bool:
        request_id = await self._msg91.send_otp(identifier)
        return request_id is not None

    async def verify_otp(self, identifier: str, otp: str) -> bool:
        return await self._msg91.verify_otp(identifier, otp)


def _redis_key(email: str) -> str:
    return f"email_otp:{email.strip().lower()}"


def _hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode("utf-8")).hexdigest()


class EmailOtpChannel(OtpChannel):
    """Brevo is a plain SMTP relay with no OTP API of its own, so — unlike
    Msg91OtpChannel — this channel owns the whole OTP lifecycle itself:
    generate a code, hash+store it in Redis with a TTL (same pattern as
    `pending_order:{order_id}` in order_service.py), email it, then compare
    the hash on verify.
    """

    def __init__(self) -> None:
        self._email = EmailService()

    async def send_otp(self, identifier: str) -> bool:
        if not self._email.is_enabled():
            return False
        otp = "".join(secrets.choice("0123456789") for _ in range(settings.email_otp_length))
        redis = await redis_client.get_client()
        await redis.set(_redis_key(identifier), _hash_otp(otp), ex=settings.email_otp_expiry_seconds)
        subject, html = render_otp_email(
            otp, expiry_minutes=max(1, settings.email_otp_expiry_seconds // 60)
        )
        return await self._email.send(identifier, subject, html)

    async def verify_otp(self, identifier: str, otp: str) -> bool:
        redis = await redis_client.get_client()
        key = _redis_key(identifier)
        stored = await redis.get(key)
        if not stored or stored != _hash_otp(otp):
            return False
        await redis.delete(key)
        return True
