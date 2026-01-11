from typing import Optional, Literal
from pydantic import BaseModel, Field
from bson import ObjectId
from src.models.product import PyObjectId, Media


class Discount(BaseModel):
    rate: float = 0
    type: Literal["percentage", "direct"] = "percentage"


class Category(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    name: str
    medias: list[Media] = []
    description: str = ""
    discount: Discount = Field(default_factory=lambda: Discount())
    
    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str}
    }


class CategoryCreate(BaseModel):
    name: str
    medias: list[Media] = []
    description: str = ""
    discount: Discount = Field(default_factory=lambda: Discount())

