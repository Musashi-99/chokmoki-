from typing import Optional
from pydantic import BaseModel, Field
from bson import ObjectId
from src.models.product import PyObjectId
from src.security.mass_assignment import StrictUpdateModel

class JewelryCategory(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    slug: str
    name: str
    tagline: str = ""
    banner: str = ""
    thumbnail: str = ""
    description: str = ""
    sort_order: int = 0
    active: bool = True
    
    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str}
    }


class JewelryCategoryCreate(BaseModel):
    slug: str
    name: str
    tagline: str = ""
    banner: str = ""
    thumbnail: str = ""
    description: str = ""
    sort_order: int = 0
    active: bool = True


class JewelryCategoryUpdate(StrictUpdateModel):
    slug: Optional[str] = None
    name: Optional[str] = None
    tagline: Optional[str] = None
    banner: Optional[str] = None
    thumbnail: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None
    active: Optional[bool] = None
