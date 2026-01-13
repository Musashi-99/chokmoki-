from typing import Optional
from pydantic import BaseModel, Field, field_validator
from bson import ObjectId
from datetime import datetime
from src.models.product import PyObjectId


class Rating(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    order_id: str
    product_id: str
    user_email: str
    rating: float = Field(..., ge=1.0, le=5.0)
    comment: str = Field(default="", max_length=2000)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    @field_validator("rating")
    @classmethod
    def validate_rating(cls, v):
        if not isinstance(v, (int, float)):
            raise ValueError("Rating must be a number")
        if v < 1.0 or v > 5.0:
            raise ValueError("Rating must be between 1.0 and 5.0")
        return float(v)
    
    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()}
    }


class RatingCreate(BaseModel):
    order_id: str
    product_id: str
    email: str
    rating: float = Field(..., ge=1.0, le=5.0)
    comment: str = Field(default="", max_length=2000)
    
    @field_validator("rating")
    @classmethod
    def validate_rating(cls, v):
        if not isinstance(v, (int, float)):
            raise ValueError("Rating must be a number")
        if v < 1.0 or v > 5.0:
            raise ValueError("Rating must be between 1.0 and 5.0")
        return float(v)
