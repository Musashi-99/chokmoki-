from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId
from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("REDIS_URL", "redis://localhost")
os.environ.setdefault("RAZORPAY_KEY_ID", "rzp_test")
os.environ.setdefault("RAZORPAY_KEY_SECRET", "secret")

from src.models.coupon import (
    CouponCreate,
    CouponUpdate,
    DiscountIndicator,
    DiscountType,
)
from src.services.discount_service import CouponService


def _create_payload(**kwargs) -> CouponCreate:
    defaults = dict(
        code="SAVE10",
        type=DiscountType.CART,
        amount=10,
        indicator=DiscountIndicator.PERCENT,
    )
    defaults.update(kwargs)
    return CouponCreate(**defaults)


def _coupon_doc(*, active: bool = True, code: str = "SAVE10") -> dict:
    now = datetime.now(timezone.utc)
    return {
        "_id": ObjectId(),
        "code": code,
        "type": "CART",
        "amount": 10.0,
        "indicator": "PERCENT",
        "product_id": None,
        "active": active,
        "created_at": now,
        "updated_at": now,
    }


def _mock_db(collection: AsyncMock):
    database = MagicMock()
    database.__getitem__ = MagicMock(return_value=collection)
    return patch(
        "src.database.connection.db.get_database",
        new_callable=AsyncMock,
        return_value=database,
    )


class TestCouponUpdate:
    def test_amount_zero_rejected(self):
        with pytest.raises(ValidationError):
            CouponUpdate(amount=0)

    def test_amount_negative_rejected(self):
        with pytest.raises(ValidationError):
            CouponUpdate(amount=-1)

    def test_percent_amount_101_rejected(self):
        with pytest.raises(ValidationError):
            CouponUpdate(indicator=DiscountIndicator.PERCENT, amount=101)


class TestCouponService:
    @pytest.mark.asyncio
    async def test_create_duplicate_raises(self):
        collection = AsyncMock()
        collection.find_one = AsyncMock(return_value=None)
        collection.insert_one = AsyncMock(side_effect=DuplicateKeyError("E11000"))

        with _mock_db(collection):
            with pytest.raises(ValueError, match="Coupon code already exists"):
                await CouponService().create(_create_payload())

    @pytest.mark.asyncio
    async def test_get_by_code_uppercases_strips_and_returns_inactive(self):
        doc = _coupon_doc(active=False, code="SAVE10")
        collection = AsyncMock()
        collection.find_one = AsyncMock(return_value=doc)

        with _mock_db(collection):
            coupon = await CouponService().get_by_code("  save10  ")

        assert coupon is not None
        assert coupon.code == "SAVE10"
        assert coupon.active is False
        collection.find_one.assert_called_once_with({"code": "SAVE10"})
