from typing import Optional
from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime
from src.models.product import PyObjectId


class HistoryPageSettings(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    settings_key: str = "main"
    page_title: str = ""
    hero_alt: str = ""
    hero_title: str = ""
    hero_intro: str = ""
    section1_label: str = ""
    section1_title: str = ""
    section1_p1: str = ""
    section1_p2: str = ""
    section2_label: str = ""
    section2_title: str = ""
    section2_p1: str = ""
    section2_p2: str = ""
    cta_title: str = ""
    cta_body: str = ""
    cta_button_label: str = ""
    cta_to: str = "/products"
    active: bool = True
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()},
    }


class HistoryPageSettingsUpdate(BaseModel):
    page_title: Optional[str] = None
    hero_alt: Optional[str] = None
    hero_title: Optional[str] = None
    hero_intro: Optional[str] = None
    section1_label: Optional[str] = None
    section1_title: Optional[str] = None
    section1_p1: Optional[str] = None
    section1_p2: Optional[str] = None
    section2_label: Optional[str] = None
    section2_title: Optional[str] = None
    section2_p1: Optional[str] = None
    section2_p2: Optional[str] = None
    cta_title: Optional[str] = None
    cta_body: Optional[str] = None
    cta_button_label: Optional[str] = None
    cta_to: Optional[str] = None
    active: Optional[bool] = None
