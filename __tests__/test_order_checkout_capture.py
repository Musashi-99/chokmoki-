from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

os.environ["ENVIRONMENT"] = "development"
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("RAZORPAY_KEY_ID", "rzp_test")
os.environ.setdefault("RAZORPAY_KEY_SECRET", "secret")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models.order import OrderCreateInput, OrderItemInput, OrderPricingInput, ShippingAddress
from src.services.order_service import OrderService


def _order_data(user_id=None):
    return OrderCreateInput(
        shippingAddress=ShippingAddress(
            email="priya@example.com",
            full_name="Priya Sen",
            phone="9876543210",
            address_line1="12 Park Street",
            city="Kolkata",
            state="West Bengal",
            postal_code="700016",
            country="India",
        ),
        items=[
            OrderItemInput(
                productId="p1",
                productName="Ring",
                variant={"default": "default"},
                quantity=1,
                price=1500,
                total=1500,
            )
        ],
        pricing=OrderPricingInput(subtotal=1500, discount=0, shipping=0, total=1500),
        userEmail="priya@example.com",
        timestamp="2026-08-14T00:00:00Z",
        paymentMethod="cod",
        user_id=user_id,
    )


@pytest.mark.asyncio
async def test_attach_checkout_account_returns_captured_id():
    data = _order_data()
    with patch("src.services.order_service.UserService") as mock_cls:
        mock_cls.return_value.capture_from_checkout = AsyncMock(return_value="usr_guest")
        result = await OrderService()._attach_checkout_account(data)
    assert result == "usr_guest"
    mock_cls.return_value.capture_from_checkout.assert_awaited_once()


@pytest.mark.asyncio
async def test_attach_checkout_account_does_not_fail_the_order():
    data = _order_data(user_id="usr_session")
    with patch("src.services.order_service.UserService") as mock_cls:
        mock_cls.return_value.capture_from_checkout = AsyncMock(side_effect=RuntimeError("mongo down"))
        result = await OrderService()._attach_checkout_account(data)
    assert result == "usr_session"
