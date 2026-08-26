from typing import Optional
from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime
from src.models.product import PyObjectId


class ContactPageSettings(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    settings_key: str = "main"
    page_title: str = ""
    postcard_eyebrow: str = ""
    postcard_title: str = ""
    postcard_intro: str = ""
    postcard_image_url: str = ""
    studio_eyebrow: str = ""
    studio_title: str = ""
    studio_tagline: str = ""
    studio_email_label: str = ""
    studio_address_label: str = ""
    studio_follow_label: str = ""
    directions_cta_label: str = ""
    active: bool = True
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()},
    }


class ContactPageSettingsUpdate(BaseModel):
    page_title: Optional[str] = None
    postcard_eyebrow: Optional[str] = None
    postcard_title: Optional[str] = None
    postcard_intro: Optional[str] = None
    postcard_image_url: Optional[str] = None
    studio_eyebrow: Optional[str] = None
    studio_title: Optional[str] = None
    studio_tagline: Optional[str] = None
    studio_email_label: Optional[str] = None
    studio_address_label: Optional[str] = None
    studio_follow_label: Optional[str] = None
    directions_cta_label: Optional[str] = None
    active: Optional[bool] = None
