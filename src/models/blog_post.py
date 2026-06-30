from typing import Optional
from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime
from src.models.product import PyObjectId


class BlogPost(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    slug: str
    title: str
    excerpt: str = ""
    image_url: str = ""
    date_label: str = ""
    read_time: str = ""
    body: str = ""
    link_to: str = "/story"
    featured: bool = False
    sort_order: int = 0
    active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()},
    }


class BlogPostCreate(BaseModel):
    slug: str
    title: str
    excerpt: str = ""
    image_url: str = ""
    date_label: str = ""
    read_time: str = ""
    body: str = ""
    link_to: str = "/story"
    featured: bool = False
    sort_order: int = 0
    active: bool = True


from src.security.mass_assignment import StrictUpdateModel


class BlogPostUpdate(StrictUpdateModel):
    slug: Optional[str] = None
    title: Optional[str] = None
    excerpt: Optional[str] = None
    image_url: Optional[str] = None
    date_label: Optional[str] = None
    read_time: Optional[str] = None
    body: Optional[str] = None
    link_to: Optional[str] = None
    featured: Optional[bool] = None
    sort_order: Optional[int] = None
    active: Optional[bool] = None


class JournalPageSettings(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    settings_key: str = "main"
    page_eyebrow: str = ""
    page_title: str = ""
    page_intro: str = ""
    philosophy_eyebrow: str = ""
    philosophy_title: str = ""
    philosophy_body: str = ""
    philosophy_image_url: str = ""
    feature_image_url: str = ""
    feature_title: str = ""
    feature_excerpt: str = ""
    feature_date: str = ""
    feature_read_time: str = ""
    feature_link_to: str = "/story"
    philosophy_cta_label: str = ""
    philosophy_cta_to: str = "/story"
    closing_eyebrow: str = ""
    closing_title: str = ""
    closing_shop_label: str = ""
    closing_shop_to: str = "/products"
    closing_story_label: str = ""
    closing_story_to: str = "/story"
    more_section_label: str = ""
    featured_label: str = ""
    read_story_label: str = ""
    read_more_label: str = ""
    active: bool = True
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()},
    }


class JournalPageSettingsUpdate(BaseModel):
    page_eyebrow: Optional[str] = None
    page_title: Optional[str] = None
    page_intro: Optional[str] = None
    philosophy_eyebrow: Optional[str] = None
    philosophy_title: Optional[str] = None
    philosophy_body: Optional[str] = None
    philosophy_image_url: Optional[str] = None
    feature_image_url: Optional[str] = None
    feature_title: Optional[str] = None
    feature_excerpt: Optional[str] = None
    feature_date: Optional[str] = None
    feature_read_time: Optional[str] = None
    feature_link_to: Optional[str] = None
    philosophy_cta_label: Optional[str] = None
    philosophy_cta_to: Optional[str] = None
    closing_eyebrow: Optional[str] = None
    closing_title: Optional[str] = None
    closing_shop_label: Optional[str] = None
    closing_shop_to: Optional[str] = None
    closing_story_label: Optional[str] = None
    closing_story_to: Optional[str] = None
    more_section_label: Optional[str] = None
    featured_label: Optional[str] = None
    read_story_label: Optional[str] = None
    read_more_label: Optional[str] = None
    active: Optional[bool] = None
