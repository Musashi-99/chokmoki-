from typing import List, Optional
from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime
from src.models.product import PyObjectId


class PolicyPageMeta(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    meta_key: str = "main"
    page_eyebrow: str = ""
    page_title: str = ""
    page_intro: str = ""
    last_updated_label: str = ""
    active: bool = True
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()},
    }


class PolicySection(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    slug: str
    title: str = ""
    body: str = ""
    sort_order: int = 0
    active: bool = True
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()},
    }


class PolicySectionCreate(BaseModel):
    slug: str
    title: str = ""
    body: str = ""
    sort_order: int = 0
    active: bool = True


from src.security.mass_assignment import StrictUpdateModel


class PolicySectionUpdate(StrictUpdateModel):
    title: Optional[str] = None
    body: Optional[str] = None
    sort_order: Optional[int] = None
    active: Optional[bool] = None


class PolicyPageMetaUpdate(BaseModel):
    page_eyebrow: Optional[str] = None
    page_title: Optional[str] = None
    page_intro: Optional[str] = None
    last_updated_label: Optional[str] = None
    active: Optional[bool] = None
