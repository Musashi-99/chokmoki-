from typing import List, Optional
from pydantic import BaseModel, Field
from pydantic_core import core_schema
from bson import ObjectId


class PyObjectId(ObjectId):
    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)
    
    @classmethod
    def validate(cls, v):
        if isinstance(v, ObjectId):
            return v
        if isinstance(v, str):
            if not ObjectId.is_valid(v):
                raise ValueError("Invalid objectid")
            return ObjectId(v)
        raise ValueError("Invalid objectid")
    
    @classmethod
    def __get_pydantic_json_schema__(cls, field_schema, handler):
        field_schema.update(type="string")
        return field_schema


class Media(BaseModel):
    url: str
    mimetype: str
    size: int


class VariantValue(BaseModel):
    label: str
    active: bool = True


class ProductVariant(BaseModel):
    variant_name: str
    variant_values: List[VariantValue]


class Product(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    name: str
    brand: str
    categories: List[PyObjectId] = []
    product_description: str = ""
    mrp_price: float
    selling_price: float
    tags: List[str] = []
    medias: List[Media] = []
    features: List[str] = []
    active: bool = True
    product_variants: List[ProductVariant] = []
    
    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str}
    }


class ProductCreate(BaseModel):
    name: str
    brand: str
    categories: List[str] = []
    product_description: str = ""
    mrp_price: float
    selling_price: float
    tags: List[str] = []
    medias: List[Media] = []
    features: List[str] = []
    active: bool = True
    product_variants: List[ProductVariant] = []

