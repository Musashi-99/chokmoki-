from typing import Optional
from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime
from src.models.product import PyObjectId


class HeroConfig(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    media_type: str = "image"  # "image" or "video"
    media_url: str
    alt_text: str = ""
    active: bool = True
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()}
    }


class HeroConfigCreate(BaseModel):
    media_type: str = "image"
    media_url: str
    alt_text: str = ""
    active: bool = True
