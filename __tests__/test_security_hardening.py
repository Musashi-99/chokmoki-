"""TDD: CQRS PII lock, OTP lockout, OpenAPI off in prod, coupon/otp rate rules."""

from __future__ import annotations

import os
import sys

os.environ.setdefault("ENVIRONMENT", "development")
os.environ["ENVIRONMENT"] = "development"
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("RAZORPAY_KEY_ID", "rzp_test")
os.environ.setdefault("RAZORPAY_KEY_SECRET", "secret")

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import Settings
from src.cqrs.router import CQRSRouter
from src.plugins.customer_deps import enforce_customer_csrf
from src.plugins.rate_limit_config import load_rate_limit_rules, match_rules, resolve_rate_limits
from src.security.client_ip import AUTH_SENSITIVE_PATHS, should_fail_closed_for_path
from src.security.exceptions import AuthorizationError
from src.security.login_lockout import LoginLockoutService
from src.security.openapi import fastapi_docs_kwargs


class TestCQRSPiiRequiresAdmin:
    @pytest.mark.asyncio
    async def test_order_list_with_email_requires_admin(self):
        with pytest.raises(AuthorizationError):
            await CQRSRouter.execute_query(
                "order.list",
                {"userEmail": "victim@example.com", "limit": 20},
            )

    @pytest.mark.asyncio
    async def test_order_get_matching_email_requires_admin(self):
        with pytest.raises(AuthorizationError):
            await CQRSRouter.execute_query(
                "order.get",
                {"id": "order-1", "userEmail": "owner@example.com"},
            )

    @pytest.mark.asyncio
    async def test_shipping_address_list_requires_admin(self):
        with pytest.raises(AuthorizationError):
            await CQRSRouter.execute_query(
                "shippingAddress.list",
                {"email": "victim@example.com"},
            )

    @pytest.mark.asyncio
    async def test_shipping_address_get_matching_email_requires_admin(self):
        with pytest.raises(AuthorizationError):
            await CQRSRouter.execute_query(
                "shippingAddress.get",
                {
                    "id": "507f1f77bcf86cd799439011",
                    "email": "owner@example.com",
                },
            )

    @pytest.mark.asyncio
    async def test_shipping_address_create_requires_admin(self):
        with pytest.raises(AuthorizationError):
            await CQRSRouter.execute_mutation(
                "shippingAddress.create",
                {
                    "email": "victim@example.com",
                    "full_name": "X",
                    "phone": "9876543210",
                    "address_line1": "1 St",
                    "city": "Kolkata",
                    "state": "WB",
                    "postal_code": "700016",
                    "country": "India",
                },
            )

    @pytest.mark.asyncio
    async def test_admin_can_still_list_orders(self):
        with patch.object(
            CQRSRouter, "_is_admin", new_callable=AsyncMock, return_value=True
        ), patch.object(
            CQRSRouter.QUERIES["order.list"], "execute", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = {"data": [], "count": 0}
            result = await CQRSRouter.execute_query(
                "order.list",
                {"userEmail": "anyone@example.com"},
                admin_key="valid-admin-jwt",
            )
            assert result["count"] == 0


class TestOtpLockoutKind:
    def test_otp_kind_uses_separate_redis_prefix(self):
        admin = LoginLockoutService()
        otp = LoginLockoutService(kind="otp")
        assert admin.LOCKOUT_PREFIX != otp.LOCKOUT_PREFIX
        assert "otp" in otp.LOCKOUT_PREFIX


class TestOtpRateLimitRule:
    def test_otp_verify_has_dedicated_rule(self, monkeypatch):
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")
        rules = load_rate_limit_rules()
        matched = match_rules(
            rules, method="POST", path="/api/auth/otp/verify", operation=None
        )
        ids = [r.id for r in matched]
        assert "otp_verify" in ids

    def test_otp_verify_excludes_public_fallback(self, monkeypatch):
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")
        rules = load_rate_limit_rules()
        resolved = resolve_rate_limits(
            rules,
            method="POST",
            path="/api/auth/otp/verify",
            operation=None,
            ip="203.0.113.9",
            admin_email=None,
            body_fields={"identifier": "buyer@example.com"},
        )
        assert any(r.rule_id == "otp_verify" for r in resolved)
        assert all(r.rule_id != "public_post_fallback" for r in resolved)

    def test_coupon_preview_has_dedicated_rule(self, monkeypatch):
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")
        rules = load_rate_limit_rules()
        resolved = resolve_rate_limits(
            rules,
            method="POST",
            path="/api/coupons/preview",
            operation=None,
            ip="203.0.113.9",
            admin_email=None,
            body_fields={"code": "SAVE10"},
        )
        assert any(r.rule_id == "coupons_preview" for r in resolved)
        assert all(r.rule_id != "public_post_fallback" for r in resolved)


class TestOpenApiDisabledInProduction:
    def test_production_hides_docs(self):
        kwargs = fastapi_docs_kwargs(True)
        assert kwargs["docs_url"] is None
        assert kwargs["redoc_url"] is None
        assert kwargs["openapi_url"] is None

    def test_development_keeps_docs(self):
        kwargs = fastapi_docs_kwargs(False)
        assert kwargs == {}


class TestOtpPathFailClosed:
    def test_otp_verify_is_auth_sensitive(self):
        assert "/api/auth/otp/verify" in AUTH_SENSITIVE_PATHS

    def test_otp_verify_fails_closed(self, monkeypatch):
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")
        monkeypatch.setenv("RATE_LIMIT_AUTH_FAIL_CLOSED", "true")
        monkeypatch.setenv("RATE_LIMIT_FAIL_CLOSED", "false")
        assert should_fail_closed_for_path("/api/auth/otp/verify") is True



class TestCustomerCsrf:
    @pytest.mark.asyncio
    async def test_get_skips_csrf(self, monkeypatch):
        monkeypatch.setattr("src.plugins.customer_deps.settings.csrf_enabled", True)
        request = MagicMock()
        request.method = "GET"
        request.cookies = {}
        request.headers = {}
        await enforce_customer_csrf(request)

    @pytest.mark.asyncio
    async def test_patch_without_token_is_403(self, monkeypatch):
        monkeypatch.setattr("src.plugins.customer_deps.settings.csrf_enabled", True)
        request = MagicMock()
        request.method = "PATCH"
        request.cookies = {}
        request.headers = {}
        with pytest.raises(HTTPException) as exc:
            await enforce_customer_csrf(request)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_matching_cookie_and_header_pass(self, monkeypatch):
        monkeypatch.setattr("src.plugins.customer_deps.settings.csrf_enabled", True)
        request = MagicMock()
        request.method = "PATCH"
        request.cookies = {"chokmoki_customer_csrf": "tok-1"}
        request.headers = {"X-CSRF-Token": "tok-1"}
        await enforce_customer_csrf(request)

    @pytest.mark.asyncio
    async def test_mismatched_token_is_403(self, monkeypatch):
        monkeypatch.setattr("src.plugins.customer_deps.settings.csrf_enabled", True)
        request = MagicMock()
        request.method = "PATCH"
        request.cookies = {"chokmoki_customer_csrf": "tok-1"}
        request.headers = {"X-CSRF-Token": "tok-2"}
        with pytest.raises(HTTPException) as exc:
            await enforce_customer_csrf(request)
        assert exc.value.status_code == 403


class TestCustomerJwtDefault:
    def test_access_ttl_default_is_one_hour(self):
        assert Settings.model_fields["customer_jwt_access_ttl_minutes"].default == 60
