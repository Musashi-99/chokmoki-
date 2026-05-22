from typing import Optional
from pydantic import BaseModel, Field, model_validator
from bson import ObjectId
from datetime import datetime
from src.models.product import PyObjectId


def _normalize_media_type(value: Optional[str]) -> str:
    return "video" if (value or "").strip().lower() == "video" else "image"


class HeroConfig(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    # Legacy single URL — kept for older records; desktop/mobile take precedence on the client
    media_type: str = "image"
    media_url: str = ""
    media_type_desktop: Optional[str] = None
    media_url_desktop: Optional[str] = None
    media_type_mobile: Optional[str] = None
    media_url_mobile: Optional[str] = None
    alt_text: str = ""
    active: bool = True
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()},
    }


class HeroConfigCreate(BaseModel):
    media_type: str = "image"
    media_url: str = ""
    media_type_desktop: Optional[str] = None
    media_url_desktop: Optional[str] = None
    media_type_mobile: Optional[str] = None
    media_url_mobile: Optional[str] = None
    alt_text: str = ""
    active: bool = True

    @model_validator(mode="after")
    def normalize_responsive_media(self) -> "HeroConfigCreate":
        desktop_url = (self.media_url_desktop or self.media_url or "").strip()
        mobile_url = (self.media_url_mobile or self.media_url or desktop_url).strip()
        desktop_type = _normalize_media_type(self.media_type_desktop or self.media_type)
        mobile_type = _normalize_media_type(self.media_type_mobile or self.media_type or desktop_type)

        if not desktop_url and not mobile_url:
            raise ValueError("Provide at least one hero media URL (desktop or mobile).")

        self.media_url_desktop = desktop_url
        self.media_url_mobile = mobile_url
        self.media_type_desktop = desktop_type
        self.media_type_mobile = mobile_type
        self.media_url = desktop_url or mobile_url
        self.media_type = desktop_type
        return self
