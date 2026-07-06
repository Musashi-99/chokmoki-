from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime
from src.models.product import PyObjectId
from src.models.shipping_address import ShippingAddress as ShippingAddressModel


class ShippingAddress(BaseModel):
    _id: Optional[str] = None
    email: str
    full_name: str
    phone: str
    address_line1: str
    address_line2: Optional[str] = ""
    city: str
    state: Optional[str] = ""
    postal_code: str
    country: str
    is_default: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class OrderItemInput(BaseModel):
    productId: str
    productName: str
    variant: Dict[str, str]  # Keep as dict for variant flexibility
    quantity: int = Field(ge=1)
    price: float
    total: float
    size: Optional[str] = None


class OrderPricingInput(BaseModel):
    subtotal: float
    discount: float
    shipping: float
    total: float


class OrderCreateInput(BaseModel):
    shippingAddress: ShippingAddress
    items: List[OrderItemInput]
    specialMessage: Optional[str] = ""
    pricing: OrderPricingInput
    userEmail: str
    timestamp: str
    paymentMethod: Optional[Literal["razorpay", "cod"]] = "cod"


class ValidatedOrderItem(BaseModel):
    product_id: str
    product_name: str
    variant: Dict[str, str]  # Keep as dict for variant flexibility
    quantity: int = Field(ge=1)
    unit_price: float
    total_price: float
    size: Optional[str] = None


class OrderStatusExtras(BaseModel):
    """DTO for order status extras"""
    pass  # Will be populated dynamically


class OrderStatus(BaseModel):
    type: Literal[
        "accepted",
        "rejected",
        "rejected_by_user",
        "delivered",
        "out_for_delivery",
        "agent",
        "agent_changed",
        "in_hub"
    ]
    reason: str = ""
    extras: Dict[str, Any] = {}  # Keep flexible for dynamic data


class ShippingAddressInOrder(BaseModel):
    """DTO for shipping address within order"""
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


class Order(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    order_id: str
    user_email: str
    shipping_address: ShippingAddressInOrder  # Changed from Dict to DTO
    items: List[ValidatedOrderItem]
    special_message: Optional[str] = ""
    subtotal: float
    discount: float
    shipping: float
    total_amount: float
    payment_method: Optional[Literal["razorpay", "cod"]] = "cod"
    payment_status: Optional[Literal["pending", "completed", "failed"]] = None
    razorpay_order_id: Optional[str] = None
    razorpay_payment_id: Optional[str] = None
    status: OrderStatus = Field(default_factory=lambda: OrderStatus(type="accepted"))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    raw_order_log: Dict[str, Any]  # Keep as dict for raw log flexibility

    # --- Warehouse fulfillment + Shiprocket shipping (independent of
    # payment_status and status.type — see src/services/shiprocket_service.py)
    fulfillment_status: Literal["pending", "packed", "shipped"] = "pending"
    shiprocket_order_id: Optional[int] = None
    shiprocket_shipment_id: Optional[int] = None
    awb_code: Optional[str] = None
    courier_name: Optional[str] = None
    courier_company_id: Optional[int] = None
    tracking_url: Optional[str] = None
    shipping_label_url: Optional[str] = None
    shipping_invoice_url: Optional[str] = None
    shipment_status: Literal[
        "pending",
        "awb_assigned",
        "pickup_scheduled",
        "picked_up",
        "in_transit",
        "out_for_delivery",
        "delivered",
        "rto_initiated",
        "rto_delivered",
        "cancelled",
        "failed",
    ] = "pending"
    shipment_status_history: List[Dict[str, Any]] = Field(default_factory=list)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()}
    }

