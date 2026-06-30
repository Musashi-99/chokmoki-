"""Phase 2 authentication and authorization tests."""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models.admin_rbac import AdminRole, role_has_permission
from src.security.exceptions import MFACodeRequired
from src.services.admin_auth_service import AdminAuthService


class TestRBAC:
    def test_super_admin_has_wildcard(self):
        assert role_has_permission(AdminRole.SUPER_ADMIN.value, "orders:write") is True


class TestAdminAuthService:
    @pytest.mark.asyncio
    async def test_authenticate_rejects_invalid_password(self, monkeypatch):
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")
        monkeypatch.setenv("ADMIN_EMAIL", "admin@test.com")
        monkeypatch.setenv("ADMIN_PASSWORD", "secret-pass")

        service = AdminAuthService()
        with patch.object(
            service.lockout, "assert_not_locked", new_callable=AsyncMock
        ), patch.object(
            service.lockout, "record_failure", new_callable=AsyncMock
        ), patch.object(service.sessions, "create_session", new_callable=AsyncMock):
            result = await service.authenticate("admin@test.com", "wrong")
            assert result is None

    @pytest.mark.asyncio
    async def test_mfa_required_when_enabled_without_code(self, monkeypatch):
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")
        monkeypatch.setenv("ADMIN_EMAIL", "admin@test.com")
        monkeypatch.setenv("ADMIN_PASSWORD", "secret-pass")
        monkeypatch.setenv("ADMIN_MFA_SECRET", "JBSWY3DPEHPK3PXP")

        service = AdminAuthService()
        with patch("src.services.admin_auth_service.settings") as mock_settings:
            mock_settings.admin_email = "admin@test.com"
            mock_settings.admin_password = "secret-pass"
            mock_settings.admin_password_hash = None
            mock_settings.admin_password_configured = True
            mock_settings.admin_mfa_enabled = True
            with patch.object(
                service.lockout, "assert_not_locked", new_callable=AsyncMock
            ):
                with pytest.raises(MFACodeRequired):
                    await service.authenticate("admin@test.com", "secret-pass")


class TestAdminSessionService:
    @pytest.mark.asyncio
    async def test_revoke_session_removes_refresh_mapping(self, monkeypatch):
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")

        from src.services.admin_session_service import AdminSessionService

        service = AdminSessionService()
        mock_redis = AsyncMock()
        session_doc = json.dumps(
            {
                "email": "admin@test.com",
                "role": "super_admin",
                "refresh_token_hash": "abc",
            }
        )
        mock_redis.get = AsyncMock(return_value=session_doc)
        mock_redis.pipeline = MagicMock(
            return_value=MagicMock(
                delete=MagicMock(return_value=None),
                srem=MagicMock(return_value=None),
                execute=AsyncMock(return_value=[]),
            )
        )

        with patch(
            "src.services.admin_session_service.redis_client.get_client",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            await service.revoke_session("session-1")
            mock_redis.pipeline.assert_called_once()
