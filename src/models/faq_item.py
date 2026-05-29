from typing import Optional
from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime
from src.models.product import PyObjectId


class FAQItem(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    question: str = Field(..., max_length=500)
    answer: str = Field(..., max_length=3000)
    scope: str = "both"  # "home", "product", "both"
    sort_order: int = 0
    active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()}
    }


class FAQItemCreate(BaseModel):
    question: str
    answer: str
    scope: str = "both"
    sort_order: int = 0
    active: bool = True
