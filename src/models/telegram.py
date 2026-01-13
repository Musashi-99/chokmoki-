from typing import Dict, List
from pydantic import BaseModel, Field


class LastOrderedItemDTO(BaseModel):
    """DTO for last ordered item"""
    name: str
    quantity: int = Field(default=1, ge=1)


class AggregatedStatsDTO(BaseModel):
    """DTO for aggregated order statistics stored in Redis"""
    total_orders: int = Field(default=0, ge=0)
    total_items: int = Field(default=0, ge=0)
    total_price: float = Field(default=0.0, ge=0.0)
    last_ordered_items: List[LastOrderedItemDTO] = Field(default_factory=list, max_length=3)


class NotificationResultDTO(BaseModel):
    """DTO for notification processing result"""
    success: bool
    message: str
    orders_processed: int = Field(default=0, ge=0)
    messages_sent: int = Field(default=0, ge=0)
