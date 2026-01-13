from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class VariantDTO(BaseModel):
    """DTO for product variant"""
    variant: Dict[str, str] = Field(default_factory=dict)


class OrderStatusExtrasDTO(BaseModel):
    """DTO for order status extras"""
    extras: Dict[str, Any] = Field(default_factory=dict)


class ShippingAddressDTO(BaseModel):
    """DTO for shipping address in orders"""
    _id: Optional[str] = None
    email: str
    full_name: str
    phone: str
    address_line1: str
    address_line2: Optional[str] = ""
    city: str
    state: str
    postal_code: str
    country: str
    is_default: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class OrderLogDTO(BaseModel):
    """DTO for order log"""
    order_id: str
    raw_data: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None


class RazorpayOrderResponseDTO(BaseModel):
    """DTO for Razorpay order creation response"""
    id: str
    amount: int
    currency: str
    status: str
    notes: Optional[Dict[str, Any]] = None


class OrderInitiateResponseDTO(BaseModel):
    """DTO for order initiation response"""
    order_id: str
    razorpay_order_id: str
    razorpay_key_id: str
    amount: float


class ProductWithCategoriesDTO(BaseModel):
    """DTO for product with category details"""
    pass  # Will be populated dynamically from Product model


class RatingSummaryDTO(BaseModel):
    """DTO for rating summary"""
    average: float
    total: int
    by_star: Dict[int, int] = Field(default_factory=dict)
