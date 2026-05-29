from typing import Optional
from pydantic import BaseModel, Field
from bson import ObjectId
from src.models.product import PyObjectId


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
