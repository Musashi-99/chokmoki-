from typing import Optional
from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime
from src.models.product import PyObjectId


class ProductPageSettings(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    settings_key: str = "main"
    craft_image_url: str = ""
    craft_eyebrow: str = ""
    craft_title: str = ""
    craft_p1: str = ""
    craft_p2: str = ""
    craft_cta_label: str = ""
    craft_cta_to: str = "/story"
    banner_image_url: str = ""
    banner_eyebrow: str = ""
    banner_title: str = ""
    banner_body: str = ""
    related_title: str = ""
    related_view_all_label: str = ""
    faq_eyebrow: str = ""
    faq_title: str = ""
    active: bool = True
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()},
    }


class ProductPageSettingsUpdate(BaseModel):
    craft_image_url: Optional[str] = None
    craft_eyebrow: Optional[str] = None
    craft_title: Optional[str] = None
    craft_p1: Optional[str] = None
    craft_p2: Optional[str] = None
    craft_cta_label: Optional[str] = None
    craft_cta_to: Optional[str] = None
    banner_image_url: Optional[str] = None
    banner_eyebrow: Optional[str] = None
    banner_title: Optional[str] = None
    banner_body: Optional[str] = None
    related_title: Optional[str] = None
    related_view_all_label: Optional[str] = None
    faq_eyebrow: Optional[str] = None
    faq_title: Optional[str] = None
    active: Optional[bool] = None
