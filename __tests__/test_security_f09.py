"""F-09 legacy JWT removal tests."""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from jose import jwt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import Settings
from src.cqrs.router import CQRSRouter
from src.models.admin_rbac import AdminRole
from src.security.exceptions import AuthorizationError
from src.security.password import hash_password
from src.services.admin_auth_service import AdminAuthService

JWT_SECRET = "v9K!mQ2@nP7#xR4$wL8%zT1^yU6&hJ3*"
ADMIN_HASH = hash_password("production-admin-pass-99!")


def _legacy_admin_token(email: str = "admin@test.com") -> str:
    expire = datetime.utcnow() + timedelta(hours=1)
    payload = {
        "sub": email,
        "exp": expire,
        "type": "admin",
        "role": AdminRole.SUPER_ADMIN.value,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def _session_access_token(
    email: str,
    session_id: str,
    jti: str,
    *,
    token_type: str = "admin_access",
) -> str:
    expire = datetime.utcnow() + timedelta(hours=1)
    payload = {
        "sub": email,
        "exp": expire,
        "type": token_type,
        "role": AdminRole.SUPER_ADMIN.value,
        "sid": session_id,
        "jti": jti,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


class TestLegacyJwtRejection:
    @pytest.mark.asyncio
    async def test_verify_access_token_rejects_legacy_admin_type(self, monkeypatch):
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")
        monkeypatch.setenv("JWT_SECRET", JWT_SECRET)

        service = AdminAuthService()
        token = _legacy_admin_token()
        with patch("src.services.admin_auth_service.settings") as mock_settings:
            mock_settings.jwt_secret = JWT_SECRET
            mock_settings.jwt_secret_previous = None
            mock_settings.jwt_algorithm = "HS256"
            principal = await service.verify_access_token(token)

        assert principal is None

    @pytest.mark.asyncio
    async def test_cqrs_rejects_legacy_admin_token(self, monkeypatch):
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")
        monkeypatch.setenv("JWT_SECRET", JWT_SECRET)

        with pytest.raises(AuthorizationError):
            await CQRSRouter.execute_query(
                "order.getLog",
                {"order_id": "order-1"},
                admin_key=_legacy_admin_token(),
            )


class TestSessionBackedJwt:
    @pytest.mark.asyncio
    async def test_verify_access_token_requires_valid_session(self, monkeypatch):
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")
        monkeypatch.setenv("JWT_SECRET", JWT_SECRET)

        service = AdminAuthService()
        session_id = str(uuid.uuid4())
        jti = str(uuid.uuid4())
        token = _session_access_token("admin@test.com", session_id, jti)

        with patch("src.services.admin_auth_service.settings") as mock_settings:
            mock_settings.jwt_secret = JWT_SECRET
            mock_settings.jwt_secret_previous = None
            mock_settings.jwt_algorithm = "HS256"
            with patch.object(
                service.sessions, "is_jti_revoked", new_callable=AsyncMock, return_value=False
            ), patch.object(
                service.sessions,
                "get_session",
                new_callable=AsyncMock,
                return_value={"email": "admin@test.com", "role": "super_admin"},
            ):
                principal = await service.verify_access_token(token)

        assert principal is not None
        assert principal.session_id == session_id
        assert principal.jti == jti

    @pytest.mark.asyncio
    async def test_revoked_jti_rejected(self, monkeypatch):
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")
        monkeypatch.setenv("JWT_SECRET", JWT_SECRET)

        service = AdminAuthService()
        token = _session_access_token("admin@test.com", str(uuid.uuid4()), str(uuid.uuid4()))

        with patch("src.services.admin_auth_service.settings") as mock_settings:
            mock_settings.jwt_secret = JWT_SECRET
            mock_settings.jwt_secret_previous = None
            mock_settings.jwt_algorithm = "HS256"
            with patch.object(
                service.sessions, "is_jti_revoked", new_callable=AsyncMock, return_value=True
            ):
                assert await service.verify_access_token(token) is None


class TestLogoutRevocation:
    @pytest.mark.asyncio
    async def test_logout_always_revokes_session(self, monkeypatch):
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")

        from src.models.admin_auth import AdminPrincipal

        service = AdminAuthService()
        principal = AdminPrincipal(
            email="admin@test.com",
            role=AdminRole.SUPER_ADMIN.value,
            session_id="session-1",
            jti="jti-1",
        )

        with patch.object(
            service.sessions, "revoke_jti", new_callable=AsyncMock
        ) as mock_revoke_jti, patch.object(
            service.sessions, "revoke_session", new_callable=AsyncMock
        ) as mock_revoke_session, patch(
            "src.services.admin_auth_service.settings"
        ) as mock_settings:
            mock_settings.jwt_access_ttl_minutes = 60
            await service.logout(principal=principal)

        mock_revoke_jti.assert_awaited_once()
        mock_revoke_session.assert_awaited_once_with("session-1")


class TestProductionLegacyBearerGuard:
    def test_production_rejects_legacy_bearer_flag(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_live_example")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "razorpay-live-secret-32chars!")
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://shop.example.com")
        monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
        monkeypatch.setenv("CRON_SECRET", "cron-secret-rotation-32chars!")
        monkeypatch.setenv("METRICS_TOKEN", "metrics-token-rotation-32ch!")
        monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
        monkeypatch.setenv("ADMIN_PASSWORD_HASH", ADMIN_HASH)
        monkeypatch.setenv("FRAUD_ENABLED", "true")
        monkeypatch.setenv("IDEMPOTENCY_ENABLED", "true")
        monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
        monkeypatch.setenv("ADMIN_LEGACY_BEARER_ENABLED", "true")

        with pytest.raises(ValueError, match="ADMIN_LEGACY_BEARER_ENABLED"):
            Settings(_env_file=None)
