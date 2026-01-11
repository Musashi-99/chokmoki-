from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field
from bson import ObjectId
from src.models.product import PyObjectId


class OrderItem(BaseModel):
    product: dict
    quantity: int


class ShippingDetails(BaseModel):
    phone: str
    email: str
    clerk_token: str
    address: str


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
    extras: Dict[str, Any] = {}


class Order(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    total_amount: float
    total_discount: float = 0
    order_items: List[OrderItem] = []
    shipping_details: ShippingDetails
    status: OrderStatus = Field(default_factory=lambda: OrderStatus(type="accepted"))
    
    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str}
    }


class OrderCreate(BaseModel):
    total_amount: float
    total_discount: float = 0
    order_items: List[OrderItem] = []
    shipping_details: ShippingDetails

