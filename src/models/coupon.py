from datetime import datetime
from enum import StrEnum
from typing import List, Optional

from bson import ObjectId
from pydantic import BaseModel, Field, field_validator, model_validator

from src.models.product import PyObjectId
from src.security.mass_assignment import StrictUpdateModel


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


class Coupon(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    code: str
    type: DiscountType
    amount: float
    indicator: DiscountIndicator
    product_id: Optional[str] = None
    active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()},
    }


class CouponCreate(BaseModel):
    code: str = Field(..., pattern=r"^[A-Z0-9]{3,24}$")
    type: DiscountType
    amount: float
    indicator: DiscountIndicator
    product_id: Optional[str] = None
    active: bool = True

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
            product_id = (self.product_id or "").strip()
            if not product_id:
                raise ValueError("product_id is required for PRODUCT coupons")
            self.product_id = product_id
        else:
            self.product_id = None
        return self


class CouponUpdate(StrictUpdateModel):
    code: Optional[str] = Field(default=None, pattern=r"^[A-Z0-9]{3,24}$")
    type: Optional[DiscountType] = None
    amount: Optional[float] = None
    indicator: Optional[DiscountIndicator] = None
    product_id: Optional[str] = None
    active: Optional[bool] = None

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, v):
        if isinstance(v, str):
            return v.strip().upper()
        return v


class CouponPreviewItem(BaseModel):
    productId: str
    quantity: int = Field(ge=1)


class CouponPreviewInput(BaseModel):
    code: str
    items: List[CouponPreviewItem]
