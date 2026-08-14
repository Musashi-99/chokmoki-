from typing import Optional
from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime
from src.models.product import PyObjectId


class AccountPageSettings(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    settings_key: str = "main"
    slide_1_kicker: str = "Since 1955"
    slide_1_title: str = "Sterling silver from Kolkata."
    slide_1_body: str = (
        "92.5 sterling from our family workshop in Birati. "
        "Sign in or create an account with a one-time code."
    )
    slide_2_kicker: str = "Since 1955"
    slide_2_title: str = "Handcrafted in Birati."
    slide_2_body: str = (
        "Four generations at the bench. Sign in to save pieces and pick up where you left off."
    )
    slide_3_kicker: str = "92.5 sterling"
    slide_3_title: str = "Made in our family workshop."
    slide_3_body: str = "Every piece starts in Kolkata. A one-time code. No password."
    interval_ms: int = 5000
    fade_ms: int = 400
    active: bool = True
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()},
    }


class AccountPageSettingsUpdate(BaseModel):
    slide_1_kicker: Optional[str] = None
    slide_1_title: Optional[str] = None
    slide_1_body: Optional[str] = None
    slide_2_kicker: Optional[str] = None
    slide_2_title: Optional[str] = None
    slide_2_body: Optional[str] = None
    slide_3_kicker: Optional[str] = None
    slide_3_title: Optional[str] = None
    slide_3_body: Optional[str] = None
    interval_ms: Optional[int] = None
    fade_ms: Optional[int] = None
    active: Optional[bool] = None
