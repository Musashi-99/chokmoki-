"""F-11 fraud engine enrichment and production guard tests."""

from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import Settings
from src.fraud.enrichment import FraudEnrichmentService
from src.fraud.engine import FraudEngine
from src.fraud.models import FraudAction, FraudContext
from src.fraud.rules import load_rules
from src.services.fraud_detection_service import FraudDetectionService


class TestFraudProductionGuard:
    def test_production_requires_fraud_enabled(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_live")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret-32chars-minimum-value!!")
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://shop.example.com")
        monkeypatch.setenv("JWT_SECRET", "v9K!mQ2@nP7#xR4$wL8%zT1^yU6&hJ3*")
        monkeypatch.setenv("CRON_SECRET", "cron-secret-rotation-32chars!")
        monkeypatch.setenv("METRICS_TOKEN", "metrics-token-rotation-32ch!")
        monkeypatch.setenv("ADMIN_PASSWORD_HASH", "$2b$12$abcdefghijklmnopqrstuv")
        monkeypatch.setenv("FRAUD_ENABLED", "false")
        monkeypatch.setenv("IDEMPOTENCY_ENABLED", "true")

        with pytest.raises(ValueError, match="FRAUD_ENABLED"):
            Settings()


class TestFraudEnrichment:
    @pytest.mark.asyncio
    async def test_disposable_email_flag(self, monkeypatch):
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")
        monkeypatch.setenv("FRAUD_ENABLED", "true")

        service = FraudEnrichmentService()
        ctx = FraudContext(event_type="order_create", email="a@mailinator.com")
        with patch(
            "src.fraud.enrichment.redis_client.get_client",
            new_callable=AsyncMock,
        ) as mock_redis:
            client = AsyncMock()
            client.incr.return_value = 1
            client.expire.return_value = True
            client.set.return_value = True
            mock_redis.return_value = client
            enriched = await service.enrich(ctx=ctx, payload={"userEmail": "a@mailinator.com"})

        assert enriched["attributes"]["disposable_email"] is True

    @pytest.mark.asyncio
    async def test_duplicate_order_detected(self, monkeypatch):
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")
        monkeypatch.setenv("FRAUD_ENABLED", "true")

        service = FraudEnrichmentService()
        ctx = FraudContext(event_type="order_create", email="buyer@example.com")
        payload = {
            "userEmail": "buyer@example.com",
            "items": [{"productId": "p1", "quantity": 1, "variant": {"default": "default"}}],
        }
        with patch(
            "src.fraud.enrichment.redis_client.get_client",
            new_callable=AsyncMock,
        ) as mock_redis:
            client = AsyncMock()
            client.incr.return_value = 1
            client.expire.return_value = True
            client.set.return_value = None
            mock_redis.return_value = client
            enriched = await service.enrich(ctx=ctx, payload=payload)

        assert enriched["attributes"]["duplicate_order"] is True


class TestFraudRulesIntegration:
    def test_velocity_rule_matches(self):
        loaded = load_rules("config/fraud_rules.yaml")
        engine = FraudEngine(loaded.rule_set)
        result = engine.evaluate(
            ctx={
                "user": {"email": "ok@example.com"},
                "velocity": {"email_orders_1h": 6, "ip_orders_1h": 1, "device_orders_1h": 1},
                "attributes": {},
            }
        )
        assert result.decision.action in {
            FraudAction.MANUAL_REVIEW,
            FraudAction.CHALLENGE,
            FraudAction.REJECT,
        }
        assert any(m.rule_id == "velocity_email_burst" for m in result.decision.matched)

    @pytest.mark.asyncio
    async def test_disabled_engine_short_circuits(self, monkeypatch):
        monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")
        monkeypatch.setenv("FRAUD_ENABLED", "false")

        service = FraudDetectionService()
        decision = await service.evaluate(
            ctx=FraudContext(event_type="order_create"),
            payload={},
        )
        assert decision.action == FraudAction.ALLOW
        assert decision.rule_set_id == "disabled"
