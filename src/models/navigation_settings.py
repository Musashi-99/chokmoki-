from typing import Optional
from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime
from src.models.product import PyObjectId


class NavigationSettings(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    settings_key: str = "main"
    home_label: str = ""
    home_to: str = "/"
    best_sellers_label: str = ""
    best_sellers_to: str = "/#best-sellers"
    shop_all_label: str = ""
    shop_all_to: str = "/products"
    contact_label: str = ""
    contact_to: str = "/contact"
    policies_label: str = ""
    policies_to: str = "/policy"
    heritage_label: str = ""
    heritage_to: str = "/#heritage"
    craftsmanship_label: str = ""
    craftsmanship_to: str = "/history"
    postcard_label: str = ""
    postcard_to: str = "/contact#postcard"
    back_to_home_label: str = ""
    active: bool = True
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()},
    }


class NavigationSettingsUpdate(BaseModel):
    home_label: Optional[str] = None
    home_to: Optional[str] = None
    best_sellers_label: Optional[str] = None
    best_sellers_to: Optional[str] = None
    shop_all_label: Optional[str] = None
    shop_all_to: Optional[str] = None
    contact_label: Optional[str] = None
    contact_to: Optional[str] = None
    policies_label: Optional[str] = None
    policies_to: Optional[str] = None
    heritage_label: Optional[str] = None
    heritage_to: Optional[str] = None
    craftsmanship_label: Optional[str] = None
    craftsmanship_to: Optional[str] = None
    postcard_label: Optional[str] = None
    postcard_to: Optional[str] = None
    back_to_home_label: Optional[str] = None
    active: Optional[bool] = None
