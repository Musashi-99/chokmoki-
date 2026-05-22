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
    featured: bool = False
    sort_order: int = 0
    active: bool = True


class JournalPageSettings(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    settings_key: str = "main"
    page_eyebrow: str = ""
    page_title: str = ""
    page_intro: str = ""
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
    active: Optional[bool] = None
