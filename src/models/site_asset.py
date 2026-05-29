from typing import Optional
from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime
from src.models.product import PyObjectId


class SiteAsset(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    key: str = Field(..., min_length=1)
    asset_type: str = "image"  # "image" or "video"
    url: str
    alt_text: str = ""
    active: bool = True
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()}
    }


class SiteAssetCreate(BaseModel):
    key: str = Field(..., min_length=1)
    asset_type: str = "image"
    url: str
    alt_text: str = ""
    active: bool = True
