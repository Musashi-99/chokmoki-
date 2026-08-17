from typing import List, Optional
from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime
from src.models.product import PyObjectId


class StudioSettings(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    settings_key: str = "main"
    email: str = ""
    legal_name: str = ""
    brand_name: str = ""
    phone: str = ""
    grievance_officer: str = ""
    hours_days: str = ""
    hours_time: str = ""
    address: str = ""
    address_lines: List[str] = Field(default_factory=list)
    address_detail: str = ""
    map_lat: float = 22.662833
    map_lon: float = 88.429749
    instagram_url: str = ""
    facebook_url: str = ""
    active: bool = True
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()},
    }


class StudioSettingsUpdate(BaseModel):
    email: Optional[str] = None
    legal_name: Optional[str] = None
    brand_name: Optional[str] = None
    phone: Optional[str] = None
    grievance_officer: Optional[str] = None
    hours_days: Optional[str] = None
    hours_time: Optional[str] = None
    address: Optional[str] = None
    address_lines: Optional[List[str]] = None
    address_detail: Optional[str] = None
    map_lat: Optional[float] = None
    map_lon: Optional[float] = None
    instagram_url: Optional[str] = None
    facebook_url: Optional[str] = None
    active: Optional[bool] = None
