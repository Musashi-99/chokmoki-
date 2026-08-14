from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt

from src.config import settings
from src.models.user import CustomerAuthTokens, CustomerPrincipal, User
from src.plugins.logger import logger
from src.services.customer_session_service import CustomerSessionService
from src.services.otp_channel import EmailOtpChannel, OtpChannel
from src.services.user_service import UserService, normalize_email


class CustomerAuthService:
    """Email+OTP (Brevo) login. Mirrors AdminAuthService's JWT shape (python-jose
    HS256 access token + opaque Redis-backed refresh token) but under
    distinct `type` claims so a customer token can never be replayed
    against an admin route, even though both share JWT_SECRET/algorithm.
    """

    def __init__(self) -> None:
        self.sessions = CustomerSessionService()
        self.users = UserService()

    def _channel(self) -> OtpChannel:
        return EmailOtpChannel()

    def _decode_token(self, token: str) -> Optional[dict]:
        secrets_to_try = [settings.jwt_secret]
        if settings.jwt_secret_previous:
            secrets_to_try.append(settings.jwt_secret_previous)
        for secret in secrets_to_try:
            try:
                return jwt.decode(token, secret, algorithms=[settings.jwt_algorithm])
            except JWTError:
                continue
        return None

    def _create_access_token(self, user_id: str, phone: str, email: str, session_id: str, jti: str) -> str:
        expire = datetime.utcnow() + timedelta(minutes=settings.customer_jwt_access_ttl_minutes)
        payload = {
            "sub": user_id,
            "phone": phone,
            "email": email,
            "exp": expire,
            "type": "customer_access",
            "sid": session_id,
            "jti": jti,
        }
        return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    async def request_otp(self, identifier: str) -> bool:
        identifier = normalize_email(identifier)
        return await self._channel().send_otp(identifier)

    async def verify_otp_and_login(self, identifier: str, otp: str) -> Optional[tuple[User, CustomerAuthTokens]]:
        identifier = normalize_email(identifier)

        ok = await self._channel().verify_otp(identifier, otp)
        if not ok:
            return None

        user = await self.users.get_or_create_by_email(identifier)

        session_id, refresh_token = await self.sessions.create_session(
            user.id, phone=user.phone or "", email=user.email or ""
        )
        jti = str(uuid.uuid4())
        access_token = self._create_access_token(user.id, user.phone or "", user.email or "", session_id, jti)
        tokens = self.sessions.build_auth_tokens(
            access_token=access_token, refresh_token=refresh_token, session_id=session_id
        )
        if logger:
            logger.info(f"Customer session created for user {user.id}")
        return user, tokens

    async def verify_access_token(self, token: str) -> Optional[CustomerPrincipal]:
        payload = self._decode_token(token)
        if not payload or payload.get("type") != "customer_access":
            return None

        user_id = payload.get("sub")
        jti = payload.get("jti")
        session_id = payload.get("sid")
        if not user_id or not jti or not session_id:
            return None

        if await self.sessions.is_jti_revoked(jti):
            return None

        session = await self.sessions.get_session(session_id)
        if not session or session.get("user_id") != user_id:
            return None

        return CustomerPrincipal(
            user_id=user_id,
            phone=session.get("phone", ""),
            email=session.get("email", ""),
            session_id=session_id,
            jti=jti,
        )

    async def refresh(self, refresh_token: str) -> Optional[CustomerAuthTokens]:
        rotated = await self.sessions.rotate_refresh_token(refresh_token)
        if not rotated:
            return None
        session_id, user_id, phone, email, new_refresh = rotated
        jti = str(uuid.uuid4())
        access_token = self._create_access_token(user_id, phone, email, session_id, jti)
        return self.sessions.build_auth_tokens(
            access_token=access_token, refresh_token=new_refresh, session_id=session_id
        )

    async def logout(
        self, principal: Optional[CustomerPrincipal] = None, refresh_token: Optional[str] = None
    ) -> None:
        if principal:
            await self.sessions.revoke_jti(principal.jti, settings.customer_jwt_access_ttl_minutes * 60)
            await self.sessions.revoke_session(principal.session_id)
            return
        if refresh_token:
            session_id = await self.sessions.get_session_id_for_refresh(refresh_token)
            if session_id:
                await self.sessions.revoke_session(session_id)
