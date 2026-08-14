from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.fraud.models import FraudAction, FraudContext, FraudDecision
from src.services.order_service import OrderService


@pytest.mark.asyncio
async def test_order_create_rejected_by_fraud(monkeypatch):
    monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")
    monkeypatch.setenv("FRAUD_ENABLED", "1")

    from src.models.order import OrderCreateInput

    payload = {
        "shippingAddress": {
            "email": "x@test.com",
            "full_name": "X",
            "phone": "9999999999",
            "address_line1": "a",
            "address_line2": "",
            "city": "c",
            "state": "s",
            "postal_code": "1",
            "country": "IN",
            "is_default": False,
        },
        "items": [
            {
                "productId": "p1",
                "productName": "n",
                "variant": {"default": "default"},
                "quantity": 1,
                "price": 100,
                "total": 100,
            }
        ],
        "specialMessage": "",
        "pricing": {"subtotal": 100, "discount": 0, "shipping": 0, "total": 100},
        "userEmail": "x@test.com",
        "timestamp": "2026-06-30T00:00:00Z",
        "paymentMethod": "cod",
    }

    order_data = OrderCreateInput(**payload)

    reject_decision = FraudDecision(
        action=FraudAction.REJECT,
        risk_score=100,
        confidence=80,
        matched=[],
        rule_set_id="t",
        rule_set_version="1",
    )

    service = OrderService()

    with patch("src.services.order_service.FraudDetectionService.evaluate", new_callable=AsyncMock, return_value=reject_decision):
        with patch.object(service, "_validate_and_prepare_order", new_callable=AsyncMock, return_value=([], type("P", (), {"subtotal": 0, "discount": 0, "shipping": 0, "total": 100})(), None)):
            with pytest.raises(ValueError):
                await service.create(order_data)

