from typing import List, Optional
from pydantic import BaseModel, Field, model_validator
from bson import ObjectId
from datetime import datetime
from src.models.product import PyObjectId
from src.security.mass_assignment import StrictUpdateModel

HERO_SLIDE_COUNT = 3
DEFAULT_SLIDE_INTERVAL_SECONDS = 6
MIN_SLIDE_INTERVAL_SECONDS = 3
MAX_SLIDE_INTERVAL_SECONDS = 30


def _normalize_media_type(value: Optional[str]) -> str:
    return "video" if (value or "").strip().lower() == "video" else "image"


def _trim_slide_urls(urls: Optional[List[str]], single_url: Optional[str]) -> List[str]:
    cleaned: List[str] = []
    if urls:
        for raw in urls:
            url = (raw or "").strip()
            if url and url not in cleaned:
                cleaned.append(url)
            if len(cleaned) >= HERO_SLIDE_COUNT:
                break
    if not cleaned:
        one = (single_url or "").strip()
        if one:
            cleaned = [one]
    return cleaned


def _clamp_interval(seconds: Optional[int]) -> int:
    try:
        value = int(seconds if seconds is not None else DEFAULT_SLIDE_INTERVAL_SECONDS)
    except (TypeError, ValueError):
        value = DEFAULT_SLIDE_INTERVAL_SECONDS
    return max(MIN_SLIDE_INTERVAL_SECONDS, min(MAX_SLIDE_INTERVAL_SECONDS, value))


def _normalize_viewport(
    media_type: Optional[str],
    urls: Optional[List[str]],
    single_url: Optional[str],
    fallback_url: Optional[str],
    label: str,
) -> tuple[str, List[str]]:
    kind = _normalize_media_type(media_type)
    primary = (single_url or "").strip() or (fallback_url or "").strip()
    slides = _trim_slide_urls(urls, primary)

    if kind == "video":
        video_url = primary or (slides[0] if slides else "")
        if not video_url:
            return kind, []
        if len(slides) > 1:
            raise ValueError(f"{label}: video mode allows one file only.")
        return kind, [video_url]

    if not slides:
        return "image", []
    return "image", slides


class HeroConfig(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    media_type: str = "image"
    media_url: str = ""
    media_type_desktop: Optional[str] = None
    media_url_desktop: Optional[str] = None
    media_type_mobile: Optional[str] = None
    media_url_mobile: Optional[str] = None
    media_urls_desktop: Optional[List[str]] = None
    media_urls_mobile: Optional[List[str]] = None
    slide_interval_seconds: int = DEFAULT_SLIDE_INTERVAL_SECONDS
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
    media_urls_desktop: Optional[List[str]] = None
    media_urls_mobile: Optional[List[str]] = None
    slide_interval_seconds: Optional[int] = DEFAULT_SLIDE_INTERVAL_SECONDS
    alt_text: str = ""
    active: bool = True

    @model_validator(mode="after")
    def normalize_responsive_media(self) -> "HeroConfigCreate":
        legacy_url = (self.media_url or "").strip()

        desktop_type, desktop_slides = _normalize_viewport(
            self.media_type_desktop or self.media_type,
            self.media_urls_desktop,
            self.media_url_desktop or legacy_url,
            None,
            "Desktop",
        )
        mobile_type, mobile_slides = _normalize_viewport(
            self.media_type_mobile or self.media_type,
            self.media_urls_mobile,
            self.media_url_mobile or legacy_url,
            desktop_slides[0] if desktop_slides else None,
            "Mobile",
        )

        if not desktop_slides and not mobile_slides:
            raise ValueError("Provide hero media for desktop or mobile (3 photos or 1 video per viewport).")

        if not desktop_slides:
            desktop_slides = list(mobile_slides)
            desktop_type = mobile_type
        if not mobile_slides:
            mobile_slides = list(desktop_slides)
            mobile_type = desktop_type

        self.media_urls_desktop = desktop_slides
        self.media_urls_mobile = mobile_slides
        self.media_url_desktop = desktop_slides[0]
        self.media_url_mobile = mobile_slides[0]
        self.media_type_desktop = desktop_type
        self.media_type_mobile = mobile_type
        self.media_url = desktop_slides[0]
        self.media_type = desktop_type
        self.slide_interval_seconds = _clamp_interval(self.slide_interval_seconds)
        return self


class HeroConfigUpdate(StrictUpdateModel):
    media_type: Optional[str] = None
    media_url: Optional[str] = None
    media_type_desktop: Optional[str] = None
    media_url_desktop: Optional[str] = None
    media_type_mobile: Optional[str] = None
    media_url_mobile: Optional[str] = None
    media_urls_desktop: Optional[List[str]] = None
    media_urls_mobile: Optional[List[str]] = None
    slide_interval_seconds: Optional[int] = None
    alt_text: Optional[str] = None
    active: Optional[bool] = None
