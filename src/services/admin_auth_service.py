from __future__ import annotations

import asyncio
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt

from src.config import settings
from src.models.admin_auth import AdminPrincipal, AuthTokens, LoginResult
from src.models.admin_rbac import AdminRole
from src.security.exceptions import MFACodeRequired
from src.security.login_lockout import LoginLockoutService
from src.security.password import verify_admin_password
from src.plugins.logger import logger
from src.services.admin_session_service import AdminSessionService


class AdminAuthService:
    def __init__(self) -> None:
        self.sessions = AdminSessionService()
        self.lockout = LoginLockoutService()

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

    def _create_access_token(
        self, email: str, role: str, session_id: str, jti: str
    ) -> str:
        expire = datetime.utcnow() + timedelta(minutes=settings.jwt_access_ttl_minutes)
        payload = {
            "sub": email,
            "exp": expire,
            "type": "admin_access",
            "role": role,
            "sid": session_id,
            "jti": jti,
        }
        return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    async def verify_access_token(self, token: str) -> Optional[AdminPrincipal]:
        payload = self._decode_token(token)
        if not payload:
            return None

        if payload.get("type") != "admin_access":
            return None

        email = payload.get("sub")
        if not email:
            return None

        jti = payload.get("jti")
        session_id = payload.get("sid")
        role = payload.get("role") or AdminRole.SUPER_ADMIN.value
        if not jti or not session_id:
            return None

        if await self.sessions.is_jti_revoked(jti):
            return None

        session = await self.sessions.get_session(session_id)
        if not session or session.get("email", "").lower() != email.lower():
            return None

        return AdminPrincipal(email=email, role=role, session_id=session_id, jti=jti)

    async def verify_admin_key(self, token: str) -> Optional[AdminPrincipal]:
        """Validate CQRS/REST admin credentials with full session checks."""
        return await self.verify_access_token(token)

    def _verify_totp(self, code: Optional[str]) -> bool:
        if not settings.admin_mfa_enabled:
            return True
        if not code:
            return False
        try:
            import pyotp

            totp = pyotp.TOTP(settings.admin_mfa_secret)
            return totp.verify(code.strip(), valid_window=1)
        except Exception as exc:
            logger.error(f"MFA verification error: {exc}")
            return False

    async def authenticate(
        self,
        email: str,
        password: str,
        totp_code: Optional[str] = None,
        *,
        client_ip: Optional[str] = None,
    ) -> Optional[LoginResult]:
        ip = (client_ip or "unknown").strip() or "unknown"
        await self.lockout.assert_not_locked(ip, email)

        expected_email = (settings.admin_email or "").strip()
        if not expected_email or not settings.admin_password_configured:
            logger.error("ADMIN_EMAIL / admin credentials are not configured")
            return None

        email_ok = secrets.compare_digest(email.strip().lower(), expected_email.lower())
        password_ok = await asyncio.to_thread(
            verify_admin_password,
            password,
            password_hash=settings.admin_password_hash,
            fallback_plaintext=settings.admin_password,
        )
        if not (email_ok and password_ok):
            await self.lockout.record_failure(ip, email)
            return None

        if settings.admin_mfa_enabled:
            if not totp_code:
                raise MFACodeRequired()
            if not self._verify_totp(totp_code):
                await self.lockout.record_failure(ip, email)
                return None

        await self.lockout.record_success(ip, email)

        role = AdminRole.SUPER_ADMIN.value
        session_id, refresh_token, csrf_token = await self.sessions.create_session(
            expected_email, role
        )
        jti = str(uuid.uuid4())
        access_token = self._create_access_token(expected_email, role, session_id, jti)
        tokens = self.sessions.build_auth_tokens(
            access_token=access_token,
            refresh_token=refresh_token,
            csrf_token=csrf_token,
            session_id=session_id,
        )
        logger.info(f"Admin session created for {expected_email}")
        return LoginResult(email=expected_email, role=role, tokens=tokens)

    async def refresh(self, refresh_token: str) -> Optional[AuthTokens]:
        rotated = await self.sessions.rotate_refresh_token(refresh_token)
        if not rotated:
            return None

        session_id, email, role, new_refresh = rotated
        jti = str(uuid.uuid4())
        access_token = self._create_access_token(email, role, session_id, jti)
        csrf_token = secrets.token_urlsafe(32)
        return self.sessions.build_auth_tokens(
            access_token=access_token,
            refresh_token=new_refresh,
            csrf_token=csrf_token,
            session_id=session_id,
        )

    async def logout(
        self,
        principal: Optional[AdminPrincipal] = None,
        refresh_token: Optional[str] = None,
    ) -> None:
        if principal:
            await self.sessions.revoke_jti(
                principal.jti, settings.jwt_access_ttl_minutes * 60
            )
            await self.sessions.revoke_session(principal.session_id)
            return

        if refresh_token:
            session_id = await self.sessions.get_session_id_for_refresh(refresh_token)
            if session_id:
                await self.sessions.revoke_session(session_id)

    async def logout_all_sessions(self, email: str) -> int:
        return await self.sessions.revoke_all_user_sessions(email)
