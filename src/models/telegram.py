from typing import Dict, List
from pydantic import BaseModel, Field
from datetime import datetime


class OrderSnapshotDTO(BaseModel):
    """DTO for order snapshot stored in Redis"""
    order_id: str
    product_id: str
    product_name: str
    quantity: int = Field(default=1, ge=1)
    price: float = Field(default=0.0, ge=0.0)
    total: float = Field(default=0.0, ge=0.0)
    currency: str = Field(default="INR")
    created_at: str


class ProductAggregateDTO(BaseModel):
    """DTO for aggregated product data"""
    name: str
    quantity: int = Field(default=0, ge=0)
    total_revenue: float = Field(default=0.0, ge=0.0)


class AggregatedOrdersDTO(BaseModel):
    """DTO for aggregated orders summary"""
    total_orders: int = Field(default=0, ge=0)
    total_revenue: float = Field(default=0.0, ge=0.0)
    products: Dict[str, ProductAggregateDTO] = Field(default_factory=dict)


class NotificationResultDTO(BaseModel):
    """DTO for notification processing result"""
    success: bool
    message: str
    orders_processed: int = Field(default=0, ge=0)
    messages_sent: int = Field(default=0, ge=0)
