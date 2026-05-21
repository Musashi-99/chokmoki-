from typing import Optional
from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime
from src.models.product import PyObjectId


class CollectionSlide(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    label: str = "Collection"
    heading: str
    description: str
    image_url: str
    image_alt: str = ""
    cta_label: str = "Discover Collection"
    cta_to: str = "/products"
    sort_order: int = 0
    active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()}
    }


class CollectionSlideCreate(BaseModel):
    label: str = "Collection"
    heading: str
    description: str
    image_url: str
    image_alt: str = ""
    cta_label: str = "Discover Collection"
    cta_to: str = "/products"
    sort_order: int = 0
    active: bool = True
