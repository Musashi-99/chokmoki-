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

    def test_amount_only_101_on_existing_percent_rejected_via_create_merge(self):
        existing = CouponCreate(
            code="SAVE10",
            type=DiscountType.CART,
            amount=10,
            indicator=DiscountIndicator.PERCENT,
        )
        merged = existing.model_dump()
        merged["amount"] = 101
        with pytest.raises(ValidationError):
            CouponCreate(**merged)


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

    @pytest.mark.asyncio
    async def test_update_dict_amount_zero_rejected(self):
        with pytest.raises(ValidationError):
            await CouponService().update(str(ObjectId()), {"amount": 0})

    @pytest.mark.asyncio
    async def test_update_dict_percent_101_rejected(self):
        with pytest.raises(ValidationError):
            await CouponService().update(
                str(ObjectId()),
                {"indicator": DiscountIndicator.PERCENT, "amount": 101},
            )

    @pytest.mark.asyncio
    async def test_update_sets_exclude_unset_and_updated_at(self):
        oid = ObjectId()
        doc = _coupon_doc()
        doc["_id"] = oid
        collection = AsyncMock()
        collection.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
        collection.find_one = AsyncMock(return_value=doc)

        with _mock_db(collection):
            await CouponService().update(str(oid), {"active": False})

        filt, op = collection.update_one.call_args[0]
        assert filt == {"_id": oid}
        assert set(op["$set"].keys()) == {"active", "updated_at"}
        assert op["$set"]["active"] is False

    @pytest.mark.asyncio
    async def test_update_amount_only_150_on_percent_rejected(self):
        oid = ObjectId()
        doc = _coupon_doc()
        doc["_id"] = oid
        collection = AsyncMock()
        collection.find_one = AsyncMock(return_value=doc)
        collection.update_one = AsyncMock()

        with _mock_db(collection):
            with pytest.raises(ValidationError):
                await CouponService().update(str(oid), {"amount": 150})

        collection.update_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_missing_returns_none_before_merge(self):
        collection = AsyncMock()
        collection.find_one = AsyncMock(return_value=None)
        collection.update_one = AsyncMock()

        with _mock_db(collection):
            result = await CouponService().update(str(ObjectId()), {"amount": 150})

        assert result is None
        collection.update_one.assert_not_called()
