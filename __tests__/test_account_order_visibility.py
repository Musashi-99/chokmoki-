"""Account order history must not merge unverified phone matches."""

from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("ENVIRONMENT", "development")
os.environ["ENVIRONMENT"] = "development"
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("RAZORPAY_KEY_ID", "rzp_test")
os.environ.setdefault("RAZORPAY_KEY_SECRET", "secret")

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models.user import CustomerPrincipal, User
from api.routes import account as account_mod


def _principal(**kwargs) -> CustomerPrincipal:
    return CustomerPrincipal(
        user_id=kwargs.get("user_id", "usr_1"),
        phone=kwargs.get("phone", "9876543210"),
        email=kwargs.get("email", "buyer@example.com"),
        session_id="sid",
        jti="jti",
    )


@pytest.mark.asyncio
async def test_unverified_phone_does_not_list_by_phone():
    user = User(
        id="usr_1",
        email="buyer@example.com",
        phone="9876543210",
        phone_verified=False,
    )
    with patch.object(account_mod, "UserService") as users, patch.object(
        account_mod, "OrderService"
    ) as orders:
        users.return_value.get_by_id = AsyncMock(return_value=user)
        svc = orders.return_value
        svc.list_by_user_id = AsyncMock(return_value=[])
        svc.list_by_email = AsyncMock(return_value=[])
        svc.list_by_phone = AsyncMock(return_value=[MagicMock(order_id="stolen")])

        result = await account_mod.collect_account_orders(_principal())

        svc.list_by_phone.assert_not_awaited()
        assert result == []


@pytest.mark.asyncio
async def test_verified_phone_still_lists_by_phone():
    user = User(
        id="usr_1",
        email="buyer@example.com",
        phone="9876543210",
        phone_verified=True,
    )
    owned = MagicMock(order_id="ord_1", created_at="2026-01-01")
    with patch.object(account_mod, "UserService") as users, patch.object(
        account_mod, "OrderService"
    ) as orders:
        users.return_value.get_by_id = AsyncMock(return_value=user)
        svc = orders.return_value
        svc.list_by_user_id = AsyncMock(return_value=[])
        svc.list_by_email = AsyncMock(return_value=[])
        svc.list_by_phone = AsyncMock(return_value=[owned])

        result = await account_mod.collect_account_orders(_principal())

        svc.list_by_phone.assert_awaited_once()
        assert result[0].order_id == "ord_1"
