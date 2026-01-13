from typing import List, Optional, Any, Generic, TypeVar
from pydantic import BaseModel

T = TypeVar('T')


class QueryResponseDTO(BaseModel, Generic[T]):
    """DTO for query responses"""
    data: T
    count: Optional[int] = None


class MutationResponseDTO(BaseModel, Generic[T]):
    """DTO for mutation responses"""
    data: Optional[T] = None
    success: Optional[bool] = None
    message: Optional[str] = None


class ListResponseDTO(BaseModel, Generic[T]):
    """DTO for list responses"""
    data: List[T]
    count: int


class PricingDTO(BaseModel):
    """DTO for pricing calculations"""
    subtotal: float
    discount: float
    shipping: float
    total: float
