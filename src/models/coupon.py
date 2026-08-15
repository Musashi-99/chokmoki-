from datetime import datetime, timezone
from enum import StrEnum
from typing import List, Optional

from pydantic import BaseModel, Field, field_serializer, field_validator, model_validator

from src.models.product import PyObjectId
from src.security.mass_assignment import StrictUpdateModel


def migrate_legacy_product_id_data(data):
    if not isinstance(data, dict):
        return data
    product_ids = data.get("product_ids")
    product_id = data.get("product_id")
    if not product_ids and product_id:
        data = {**data, "product_ids": [product_id]}
    if "product_id" in data:
        data = {k: v for k, v in data.items() if k != "product_id"}
    return data


class DiscountType(StrEnum):
    CART = "CART"
    PRODUCT = "PRODUCT"


class DiscountIndicator(StrEnum):
    PERCENT = "PERCENT"
    AMOUNT = "AMOUNT"


class AppliedDiscount(BaseModel):
    code: str
    type: DiscountType
    amount: float
    indicator: DiscountIndicator
    product_ids: Optional[List[str]] = None

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_product_id(cls, data):
        return migrate_legacy_product_id_data(data)


class Coupon(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    code: str
    type: DiscountType
    amount: float
    indicator: DiscountIndicator
    product_ids: Optional[List[str]] = None
    active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
    }

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_product_id(cls, data):
        return migrate_legacy_product_id_data(data)

    @field_serializer("id")
    def serialize_id(self, value: Optional[PyObjectId]) -> Optional[str]:
        return str(value) if value is not None else None

    @field_serializer("created_at", "updated_at")
    def serialize_datetime(self, value: datetime) -> str:
        return value.isoformat()


class CouponCreate(BaseModel):
    code: str = Field(..., pattern=r"^[A-Z0-9]{3,24}$")
    type: DiscountType
    amount: float
    indicator: DiscountIndicator
    product_ids: Optional[List[str]] = None
    active: bool = True

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_product_id(cls, data):
        return migrate_legacy_product_id_data(data)

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, v):
        if isinstance(v, str):
            return v.strip().upper()
        return v

    @model_validator(mode="after")
    def validate_amount_and_scope(self):
        if self.indicator == DiscountIndicator.PERCENT:
            if not (0 < self.amount <= 100):
                raise ValueError("PERCENT amount must be greater than 0 and at most 100")
        elif self.indicator == DiscountIndicator.AMOUNT:
            if self.amount <= 0:
                raise ValueError("AMOUNT must be greater than 0")

        if self.type == DiscountType.PRODUCT:
            seen = set()
            product_ids = []
            for pid in self.product_ids or []:
                pid = (pid or "").strip()
                if pid and pid not in seen:
                    seen.add(pid)
                    product_ids.append(pid)
            if not product_ids:
                raise ValueError("At least one product is required for PRODUCT coupons")
            self.product_ids = product_ids
        else:
            self.product_ids = None
        return self


class CouponUpdate(StrictUpdateModel):
    code: Optional[str] = Field(default=None, pattern=r"^[A-Z0-9]{3,24}$")
    type: Optional[DiscountType] = None
    amount: Optional[float] = None
    indicator: Optional[DiscountIndicator] = None
    product_ids: Optional[List[str]] = None
    active: Optional[bool] = None

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_product_id(cls, data):
        return migrate_legacy_product_id_data(data)

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, v):
        if isinstance(v, str):
            return v.strip().upper()
        return v

    @model_validator(mode="after")
    def validate_amount(self):
        if self.amount is None:
            return self
        if self.indicator == DiscountIndicator.PERCENT:
            if not (0 < self.amount <= 100):
                raise ValueError("PERCENT amount must be greater than 0 and at most 100")
        elif self.amount <= 0:
            raise ValueError("amount must be greater than 0")
        return self


class CouponPreviewItem(BaseModel):
    productId: str
    quantity: int = Field(ge=1)


class CouponPreviewInput(BaseModel):
    code: str
    items: List[CouponPreviewItem] = Field(..., min_length=1, max_length=50)
