from collections.abc import Sequence
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from src.models.common import PricingDTO
from src.models.coupon import (
    AppliedDiscount,
    Coupon,
    CouponCreate,
    CouponUpdate,
    DiscountIndicator,
    DiscountType,
)
from src.utils.money import money


def _attr(obj, name):
    if isinstance(obj, dict):
        return obj[name]
    return getattr(obj, name)


def _attr_get(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def coupon_product_ids(coupon: Any) -> list[str]:
    ids = _attr_get(coupon, "product_ids") or []
    if ids:
        return [str(pid) for pid in ids]
    pid = _attr_get(coupon, "product_id")
    if pid:
        return [str(pid)]
    return []


def _coupon_allows_country(coupon: Any, country: Optional[str]) -> bool:
    countries = _attr_get(coupon, "countries") or None
    if not countries:
        return True
    if not country:
        return False
    return country.upper() in {c.upper() for c in countries}


def compute_discount(
    items: Sequence[Any],
    coupon: Any,
    shipping: float = 0,
    country: Optional[str] = None,
) -> tuple[float, float, float]:
    if not _coupon_allows_country(coupon, country):
        raise ValueError("Coupon is not valid for this region")

    subtotal = money(sum(money(_attr(item, "total_price")) for item in items))
    coupon_type = _attr(coupon, "type")
    indicator = _attr(coupon, "indicator")
    amount = _attr(coupon, "amount")

    if coupon_type == DiscountType.PRODUCT:
        product_ids = set(coupon_product_ids(coupon))
        matching = [
            item for item in items if str(_attr(item, "product_id")) in product_ids
        ]
        if not matching:
            raise ValueError("Coupon does not apply to this cart")
        eligible = money(sum(money(_attr(item, "total_price")) for item in matching))
    else:
        eligible = subtotal

    if indicator == DiscountIndicator.PERCENT:
        computed = money(Decimal(str(eligible)) * Decimal(str(amount)) / Decimal("100"))
    else:
        computed = money(min(amount, eligible))

    computed = money(min(computed, subtotal))
    total = money(max(0, subtotal - computed + money(shipping)))
    return computed, total, subtotal


class DiscountService:
    def compute(
        self,
        items: Sequence[Any],
        coupon: Any,
        shipping: float = 0,
        country: Optional[str] = None,
    ) -> tuple[float, float, float]:
        return compute_discount(items, coupon, shipping, country=country)

    async def apply(
        self,
        code: Optional[str],
        validated_items,
        shipping: float = 0,
        country: Optional[str] = None,
    ) -> tuple[PricingDTO, Optional[AppliedDiscount]]:
        items = validated_items or []
        if not (code or "").strip():
            subtotal = money(sum(money(_attr(item, "total_price")) for item in items))
            ship = money(shipping)
            return (
                PricingDTO(
                    subtotal=subtotal,
                    discount=0,
                    shipping=ship,
                    total=money(subtotal + ship),
                ),
                None,
            )

        coupon = await CouponService().get_by_code(code)
        if coupon is None:
            raise ValueError("Invalid coupon")
        if not coupon.active:
            raise ValueError("Coupon is not active")

        computed, total, subtotal = compute_discount(items, coupon, shipping, country=country)
        return (
            PricingDTO(
                subtotal=subtotal,
                discount=computed,
                shipping=money(shipping),
                total=total,
            ),
            AppliedDiscount(
                code=coupon.code,
                type=coupon.type,
                amount=coupon.amount,
                indicator=coupon.indicator,
                product_ids=(
                    coupon_product_ids(coupon)
                    if coupon.type == DiscountType.PRODUCT
                    else None
                ),
            ),
        )

    async def resolve_preview_items(self, items: Sequence[Any], country: Optional[str] = None) -> list:
        from src.services.product_service import ProductService
        from src.pricing.price_lookup import resolve_price

        product_service = ProductService()
        priced = []
        for item in items:
            product_id = _attr(item, "productId")
            quantity = _attr(item, "quantity")
            product = await product_service.get_by_id(str(product_id))
            if not product:
                raise ValueError(f"Product {product_id} not found")
            if not product.active:
                raise ValueError(f"Product {product_id} is not active")
            unit_price = (
                resolve_price(product.prices, country or "default").sellingPrice
                if product.prices
                else product.price_inr
            )
            priced.append(
                SimpleNamespace(
                    product_id=str(product.id),
                    total_price=money(Decimal(str(unit_price)) * int(quantity)),
                )
            )
        return priced


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
        existing = await self.get_by_id(coupon_id)
        if existing is None:
            return None
        merged = {
            "code": existing.code,
            "type": existing.type,
            "amount": existing.amount,
            "indicator": existing.indicator,
            "product_ids": existing.product_ids,
            "countries": existing.countries,
            "active": existing.active,
        }
        merged.update(payload)
        CouponCreate(**merged)
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
