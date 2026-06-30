from typing import Optional
from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime
from src.models.product import PyObjectId


class Testimonial(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    name: str
    initials: str = ""
    rating: int = Field(..., ge=1, le=5)
    text: str = Field(..., max_length=2000)
    location: str = ""
    active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()}
    }


class TestimonialCreate(BaseModel):
    name: str
    initials: str = ""
    rating: int = Field(..., ge=1, le=5)
    text: str = Field(..., max_length=2000)
    location: str = ""
    active: bool = True


from src.security.mass_assignment import StrictUpdateModel


class TestimonialUpdate(StrictUpdateModel):
    name: Optional[str] = None
    initials: Optional[str] = None
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    text: Optional[str] = Field(default=None, max_length=2000)
    location: Optional[str] = None
    active: Optional[bool] = None
