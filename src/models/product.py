from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
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


class MarketPrice(BaseModel):
    """One country's price for a product. "default" is the required
    fallback bucket used for every country outside the configured
    markets (see settings.supported_market_countries)."""
    country: str          # "IN" | "AU" | "NZ" | "default"
    sym: str              # display symbol, e.g. "₹" / "$"
    currency: str         # ISO 4217, e.g. "INR" / "AUD" / "NZD" / "USD"
    mrp: float
    sellingPrice: float

    @field_validator("mrp", "sellingPrice")
    @classmethod
    def _positive(cls, v):
        from src.utils.money import money
        n = money(v)
        if n <= 0:
            raise ValueError("Price must be greater than zero")
        return n

    @field_validator("country")
    @classmethod
    def _upper_country(cls, v):
        v = (v or "").strip()
        return v if v == "default" else v.upper()


def _validate_market_prices(prices: List["MarketPrice"]) -> List["MarketPrice"]:
    if not prices:
        return prices
    seen = set()
    for p in prices:
        if p.country in seen:
            raise ValueError(f"Duplicate price entry for country '{p.country}'")
        seen.add(p.country)
    if "default" not in seen:
        raise ValueError("prices must include a 'default' fallback entry")
    return prices


class JewelryProduct(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    slug: str
    name: str
    price_inr: float
    prices: List[MarketPrice] = Field(default_factory=list)
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

    @field_validator("prices")
    @classmethod
    def _validate_prices(cls, v):
        return _validate_market_prices(v)

    @model_validator(mode="after")
    def _sync_legacy_inr(self):
        # price_inr stays the source of truth for legacy paths (admin manual
        # orders, price sort) — keep it mirrored to the "IN" market bucket
        # whenever multi-region pricing is configured, so there is exactly
        # one number an editor has to keep correct.
        for p in self.prices:
            if p.country == "IN":
                self.price_inr = p.sellingPrice
                break
        return self

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str}
    }


class JewelryProductCreate(BaseModel):
    slug: str
    name: str
    price_inr: float
    prices: List[MarketPrice] = Field(default_factory=list)
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

    @field_validator("prices")
    @classmethod
    def _validate_prices(cls, v):
        return _validate_market_prices(v)

    @model_validator(mode="after")
    def _sync_legacy_inr(self):
        for p in self.prices:
            if p.country == "IN":
                self.price_inr = p.sellingPrice
                break
        return self


from src.security.mass_assignment import StrictUpdateModel


class JewelryProductUpdate(StrictUpdateModel):
    slug: Optional[str] = None
    name: Optional[str] = None
    price_inr: Optional[float] = None
    prices: Optional[List[MarketPrice]] = None
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

    @field_validator("prices")
    @classmethod
    def _validate_prices(cls, v):
        if v is None:
            return v
        return _validate_market_prices(v)

    @model_validator(mode="after")
    def _sync_legacy_inr(self):
        if self.prices:
            for p in self.prices:
                if p.country == "IN":
                    self.price_inr = p.sellingPrice
                    break
        return self


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
