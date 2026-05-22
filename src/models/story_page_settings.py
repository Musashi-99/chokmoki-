from typing import Optional
from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime
from src.models.product import PyObjectId


class StoryPageSettings(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    settings_key: str = "main"
    hero_label: str = ""
    hero_title: str = ""
    hero_intro: str = ""
    beginning_label: str = ""
    beginning_title: str = ""
    beginning_p1: str = ""
    beginning_p2: str = ""
    craft_label: str = ""
    craft_title: str = ""
    craft_p1: str = ""
    craft_p2: str = ""
    philosophy_label: str = ""
    philosophy_title: str = ""
    philosophy_p1: str = ""
    philosophy_p2: str = ""
    philosophy_p3: str = ""
    kolkata_label: str = ""
    kolkata_title: str = ""
    kolkata_p1: str = ""
    kolkata_p2: str = ""
    studio_label: str = ""
    studio_title: str = ""
    closing_label: str = ""
    closing_title: str = ""
    closing_body: str = ""
    closing_cta_label: str = ""
    closing_cta_to: str = "/products"
    closing_back_label: str = ""
    active: bool = True
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()},
    }


class StoryPageSettingsUpdate(BaseModel):
    hero_label: Optional[str] = None
    hero_title: Optional[str] = None
    hero_intro: Optional[str] = None
    beginning_label: Optional[str] = None
    beginning_title: Optional[str] = None
    beginning_p1: Optional[str] = None
    beginning_p2: Optional[str] = None
    craft_label: Optional[str] = None
    craft_title: Optional[str] = None
    craft_p1: Optional[str] = None
    craft_p2: Optional[str] = None
    philosophy_label: Optional[str] = None
    philosophy_title: Optional[str] = None
    philosophy_p1: Optional[str] = None
    philosophy_p2: Optional[str] = None
    philosophy_p3: Optional[str] = None
    kolkata_label: Optional[str] = None
    kolkata_title: Optional[str] = None
    kolkata_p1: Optional[str] = None
    kolkata_p2: Optional[str] = None
    studio_label: Optional[str] = None
    studio_title: Optional[str] = None
    closing_label: Optional[str] = None
    closing_title: Optional[str] = None
    closing_body: Optional[str] = None
    closing_cta_label: Optional[str] = None
    closing_cta_to: Optional[str] = None
    closing_back_label: Optional[str] = None
    active: Optional[bool] = None
