"""Phase 1 security hardening — unit and integration tests."""

from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import ValidationError

from src.config import INSECURE_DEFAULTS, Settings
from src.cqrs.router import CQRSRouter
from src.security.exceptions import AuthorizationError
from src.utils.regex_safe import escape_mongo_regex
from src.models.order import OrderItemInput


class TestProductionConfigGuard:
    def test_development_allows_defaults(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")
        monkeypatch.setenv("ADMIN_PASSWORD", INSECURE_DEFAULTS["admin_password"])
        monkeypatch.setenv("JWT_SECRET", INSECURE_DEFAULTS["jwt_secret"])
        settings = Settings()
        assert settings.admin_password == INSECURE_DEFAULTS["admin_password"]

    def test_production_rejects_default_secrets(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")
        monkeypatch.setenv("ADMIN_PASSWORD", INSECURE_DEFAULTS["admin_password"])
        monkeypatch.setenv("JWT_SECRET", INSECURE_DEFAULTS["jwt_secret"])
        monkeypatch.setenv("CRON_SECRET", "short")
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://shop.example.com")

        with pytest.raises(ValueError, match="Insecure production configuration"):
            Settings()


class TestCQRSOrderAuthorization:
    @pytest.mark.asyncio
    async def test_order_get_requires_email_or_admin(self):
        with pytest.raises(AuthorizationError):
            await CQRSRouter.execute_query("order.get", {"id": "order-1"})

    @pytest.mark.asyncio
    async def test_order_get_rejects_wrong_email(self):
        mock_order = MagicMock()
        mock_order.user_email = "owner@example.com"

        with patch(
            "src.cqrs.router.OrderService"
        ) as mock_service_cls:
            mock_service_cls.return_value.get_by_id = AsyncMock(return_value=mock_order)
            with pytest.raises(AuthorizationError):
                await CQRSRouter.execute_query(
                    "order.get",
                    {"id": "order-1", "userEmail": "attacker@example.com"},
                )

    @pytest.mark.asyncio
    async def test_order_get_allows_matching_email(self):
        mock_order = MagicMock()
        mock_order.user_email = "owner@example.com"

        with patch(
            "src.cqrs.router.OrderService"
        ) as mock_service_cls, patch.object(
            CQRSRouter.QUERIES["order.get"], "execute", new_callable=AsyncMock
        ) as mock_execute:
            mock_service_cls.return_value.get_by_id = AsyncMock(return_value=mock_order)
            mock_execute.return_value = {"data": {"order_id": "order-1"}}

            result = await CQRSRouter.execute_query(
                "order.get",
                {"id": "order-1", "userEmail": "owner@example.com"},
            )
            assert result["data"]["order_id"] == "order-1"

    @pytest.mark.asyncio
    async def test_order_get_log_requires_admin(self):
        with pytest.raises(AuthorizationError):
            await CQRSRouter.execute_query("order.getLog", {"order_id": "order-1"})

    @pytest.mark.asyncio
    async def test_order_update_status_requires_admin(self):
        with pytest.raises(AuthorizationError):
            await CQRSRouter.execute_mutation(
                "order.updateStatus",
                {"order_id": "order-1", "status": {"type": "delivered"}},
            )


class TestOrderQuantityValidation:
    def test_negative_quantity_rejected_by_model(self):
        with pytest.raises(ValidationError):
            OrderItemInput(
                productId="p1",
                productName="Ring",
                variant={"default": "default"},
                quantity=-1,
                price=100.0,
                total=-100.0,
            )

    def test_zero_quantity_rejected_by_model(self):
        with pytest.raises(ValidationError):
            OrderItemInput(
                productId="p1",
                productName="Ring",
                variant={"default": "default"},
                quantity=0,
                price=100.0,
                total=0.0,
            )


class TestRegexEscaping:
    def test_escape_mongo_regex_metacharacters(self):
        assert escape_mongo_regex(".*") == r"\.\*"
        assert escape_mongo_regex("(a+)+") == r"\(a\+\)\+"


class TestRazorpayAmountVerification:
    def test_verify_payment_amount_match(self, monkeypatch):
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")

        from src.services.razorpay_service import RazorpayService

        service = RazorpayService()
        service.client = MagicMock()
        service.client.payment.fetch.return_value = {
            "amount": 150000,
            "status": "captured",
        }
        assert service.verify_payment_amount("pay_123", 1500.0) is True

    def test_verify_payment_amount_mismatch(self, monkeypatch):
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")

        from src.services.razorpay_service import RazorpayService

        service = RazorpayService()
        service.client = MagicMock()
        service.client.payment.fetch.return_value = {
            "amount": 100,
            "status": "captured",
        }
        assert service.verify_payment_amount("pay_123", 1500.0) is False
