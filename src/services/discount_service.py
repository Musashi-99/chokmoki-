from collections.abc import Sequence
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from src.models.coupon import Coupon, CouponCreate, CouponUpdate, DiscountIndicator, DiscountType


def money(x) -> float:
    return float(Decimal(str(x)).quantize(Decimal("0.01"), ROUND_HALF_UP))


def _attr(obj, name):
    if isinstance(obj, dict):
        return obj[name]
    return getattr(obj, name)


def compute_discount(
    items: Sequence[Any],
    coupon: Any,
    shipping: float = 0,
) -> tuple[float, float, float]:
    subtotal = money(sum(_attr(item, "total_price") for item in items))
    coupon_type = _attr(coupon, "type")
    indicator = _attr(coupon, "indicator")
    amount = _attr(coupon, "amount")

    if coupon_type == DiscountType.PRODUCT:
        product_id = _attr(coupon, "product_id")
        matching = [item for item in items if _attr(item, "product_id") == product_id]
        if not matching:
            raise ValueError("Coupon does not apply to this cart")
        eligible = money(sum(_attr(item, "total_price") for item in matching))
    else:
        eligible = subtotal

    if indicator == DiscountIndicator.PERCENT:
        computed = money(eligible * amount / 100)
    else:
        computed = money(min(amount, eligible))

    computed = min(computed, subtotal)
    total = money(max(0, subtotal - computed + shipping))
    return computed, total, subtotal


class DiscountService:
    # apply/lookup is added in a later task
    def compute(
        self,
        items: Sequence[Any],
        coupon: Any,
        shipping: float = 0,
    ) -> tuple[float, float, float]:
        return compute_discount(items, coupon, shipping)


class CouponService:
    COLLECTION_NAME = "coupons"

    async def _collection(self):
        from src.database.connection import db

        database = await db.get_database()
        return database[self.COLLECTION_NAME]

    async def ensure_indexes(self) -> None:
        collection = await self._collection()
        await collection.create_index("code", unique=True)

    async def create(self, data: CouponCreate) -> Coupon:
        collection = await self._collection()
        existing = await collection.find_one({"code": data.code})
        if existing:
            raise ValueError("Coupon code already exists")
        now = datetime.now(timezone.utc)
        doc = data.model_dump()
        doc["created_at"] = now
        doc["updated_at"] = now
        try:
            result = await collection.insert_one(doc)
        except DuplicateKeyError:
            raise ValueError("Coupon code already exists")
        doc["_id"] = result.inserted_id
        return Coupon(**doc)

    async def list(self, active: Optional[bool] = None) -> List[Dict[str, Any]]:
        collection = await self._collection()
        query: Dict[str, Any] = {}
        if active is not None:
            query["active"] = active
        docs = await collection.find(query).to_list(length=500)
        return [Coupon(**doc).model_dump(by_alias=True) for doc in docs]

    async def get_by_id(self, coupon_id: str) -> Optional[Coupon]:
        collection = await self._collection()
        doc = await collection.find_one({"_id": ObjectId(coupon_id)})
        return Coupon(**doc) if doc else None

    async def get_by_code(self, code: str) -> Optional[Coupon]:
        collection = await self._collection()
        doc = await collection.find_one({"code": (code or "").strip().upper()})
        return Coupon(**doc) if doc else None

    async def update(
        self, coupon_id: str, update_data: CouponUpdate | Dict[str, Any]
    ) -> Optional[Coupon]:
        if not isinstance(update_data, CouponUpdate):
            update_data = CouponUpdate.model_validate(update_data)
        payload = update_data.model_dump(exclude_unset=True)
        payload["updated_at"] = datetime.now(timezone.utc)
        collection = await self._collection()
        try:
            result = await collection.update_one(
                {"_id": ObjectId(coupon_id)},
                {"$set": payload},
            )
        except DuplicateKeyError:
            raise ValueError("Coupon code already exists")
        if result.matched_count == 0:
            return None
        return await self.get_by_id(coupon_id)

    async def delete(self, coupon_id: str) -> bool:
        collection = await self._collection()
        result = await collection.delete_one({"_id": ObjectId(coupon_id)})
        return result.deleted_count > 0
