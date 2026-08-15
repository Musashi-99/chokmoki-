from typing import List, Optional
from pydantic import BaseModel, Field, field_validator
from pydantic_core import core_schema
from bson import ObjectId
from datetime import datetime


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


# Backward-compatible legacy models for order system compatibility
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


class JewelryProduct(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    slug: str
    name: str
    price_inr: float
    category: str
    collection: str
    thumbnail: str
    gallery: List[str] = []
    material: str = ""
    craftsmanship: str = ""
    shipping_details: str = ""
    care_guide: str = ""
    returns_policy: str = ""
    authenticity_details: str = ""
    description: str = ""
    story: Optional[str] = None
    sizes: List[str] = []
    is_best_seller: bool = False
    is_curated: bool = False
    best_seller_order: int = 0
    curated_order: int = 0
    weight_grams: Optional[float] = None
    package_length_cm: Optional[float] = None
    package_breadth_cm: Optional[float] = None
    package_height_cm: Optional[float] = None
    purity: str = "92.5% Sterling Silver"
    stock_status: str = "in_stock"
    stock_qty: Optional[int] = None
    active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    # Backward-compatible fields for order system
    selling_price: float = 0
    product_variants: List[ProductVariant] = []

    @field_validator("price_inr")
    @classmethod
    def _money_price(cls, v):
        from src.utils.money import money
        n = money(v)
        if n <= 0:
            raise ValueError("Price must be greater than zero")
        return n
    
    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str}
    }


class JewelryProductCreate(BaseModel):
    slug: str
    name: str
    price_inr: float
    category: str
    collection: str
    thumbnail: str
    gallery: List[str] = []
    material: str = ""
    craftsmanship: str = ""
    shipping_details: str = ""
    care_guide: str = ""
    returns_policy: str = ""
    authenticity_details: str = ""
    description: str = ""
    story: Optional[str] = None
    sizes: List[str] = []
    is_best_seller: bool = False
    is_curated: bool = False
    best_seller_order: int = 0
    curated_order: int = 0
    weight_grams: Optional[float] = None
    package_length_cm: Optional[float] = None
    package_breadth_cm: Optional[float] = None
    package_height_cm: Optional[float] = None
    purity: str = "92.5% Sterling Silver"
    stock_status: str = "in_stock"
    stock_qty: Optional[int] = None
    active: bool = True

    @field_validator("price_inr")
    @classmethod
    def _money_price(cls, v):
        from src.utils.money import money
        n = money(v)
        if n <= 0:
            raise ValueError("Price must be greater than zero")
        return n


from src.security.mass_assignment import StrictUpdateModel


class JewelryProductUpdate(StrictUpdateModel):
    slug: Optional[str] = None
    name: Optional[str] = None
    price_inr: Optional[float] = None
    category: Optional[str] = None
    collection: Optional[str] = None
    thumbnail: Optional[str] = None
    gallery: Optional[List[str]] = None
    material: Optional[str] = None
    craftsmanship: Optional[str] = None
    shipping_details: Optional[str] = None
    care_guide: Optional[str] = None
    returns_policy: Optional[str] = None
    authenticity_details: Optional[str] = None
    description: Optional[str] = None
    story: Optional[str] = None
    sizes: Optional[List[str]] = None
    is_best_seller: Optional[bool] = None
    is_curated: Optional[bool] = None
    best_seller_order: Optional[int] = None
    curated_order: Optional[int] = None
    weight_grams: Optional[float] = None
    package_length_cm: Optional[float] = None
    package_breadth_cm: Optional[float] = None
    package_height_cm: Optional[float] = None
    purity: Optional[str] = None
    stock_status: Optional[str] = None
    stock_qty: Optional[int] = None
    active: Optional[bool] = None

    @field_validator("price_inr")
    @classmethod
    def _money_price(cls, v):
        if v is None:
            return v
        from src.utils.money import money
        n = money(v)
        if n <= 0:
            raise ValueError("Price must be greater than zero")
        return n


class Product(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    name: str
    brand: str = ""
    categories: List[PyObjectId] = []
    product_description: str = ""
    mrp_price: float = 0
    selling_price: float = 0
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
    brand: str = ""
    categories: List[str] = []
    product_description: str = ""
    mrp_price: float = 0
    selling_price: float = 0
    tags: List[str] = []
    medias: List[Media] = []
    features: List[str] = []
    active: bool = True
    product_variants: List[ProductVariant] = []
