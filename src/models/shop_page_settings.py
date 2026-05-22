from typing import Optional
from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime
from src.models.product import PyObjectId


class ShopPageSettings(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    settings_key: str = "main"
    hero_image_url: str = ""
    hero_alt: str = ""
    hero_eyebrow: str = ""
    hero_title: str = ""
    hero_subtitle: str = ""
    active: bool = True
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()},
    }


class ShopPageSettingsUpdate(BaseModel):
    hero_image_url: Optional[str] = None
    hero_alt: Optional[str] = None
    hero_eyebrow: Optional[str] = None
    hero_title: Optional[str] = None
    hero_subtitle: Optional[str] = None
    active: Optional[bool] = None
