"""Seed the full Chokmoki demo catalogue (matches storefront slugs). Safe to re-run."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.seed_one_product import CATEGORIES, ensure_categories
from src.models.product import JewelryProductCreate
from src.services.product_service import ProductService

CDN_THUMB = "https://cdn.amplifycheckout.com/chokmoki/products/57ab533440db4ef5a1af188b03813434.jpg"

COMMON = {
    "collection": "Chokmoki Archive",
    "thumbnail": CDN_THUMB,
    "gallery": [CDN_THUMB],
    "craftsmanship": (
        "Handcrafted in Kolkata with traditional techniques and hand-finished surfaces."
    ),
    "shipping_details": "Complimentary Pan-India shipping. Express delivery in 3–5 business days.",
    "care_guide": "Store dry, polish gently with a soft cloth, avoid perfume and moisture.",
    "returns_policy": "14-day returns on unworn pieces in original packaging.",
    "authenticity_details": "Certified 92.5% sterling silver with studio authenticity card.",
    "purity": "92.5% Sterling Silver",
    "stock_status": "in_stock",
    "active": True,
    "weight_grams": 8.5,
}

DEMO_PRODUCTS: list[dict] = [
    {
        "slug": "wing-ring",
        "name": "Wing Ring",
        "price_inr": 42640,
        "category": "rings",
        "material": "92.5% sterling silver, hand-set stones, hypoallergenic finish",
        "description": "Spread your wings with the Chokmoki Wing Ring — bold sterling silver for quiet confidence.",
        "story": "Created for the woman who moves with quiet confidence.",
        "sizes": ["Adjustable"],
        "is_best_seller": True,
        "is_curated": True,
        "best_seller_order": 1,
        "curated_order": 1,
    },
    {
        "slug": "bee-pendant-set",
        "name": "Bee Pendant Set",
        "price_inr": 43160,
        "category": "necklaces",
        "material": "92.5% sterling silver, gold-plated detailing, hand-set stones",
        "description": "Buzz into timeless elegance with the Chokmoki Bee Pendant Set.",
        "story": "Handcrafted in Kolkata for women who carry themselves with quiet certainty.",
        "sizes": ["42 cm"],
        "is_best_seller": True,
        "is_curated": True,
        "best_seller_order": 2,
        "curated_order": 2,
    },
    {
        "slug": "butterfly-ring",
        "name": "Butterfly Ring",
        "price_inr": 39760,
        "category": "rings",
        "material": "92.5% sterling silver, hand-set premium stones",
        "description": "The Butterfly Ring — delicate sterling silver inspired by graceful movement.",
        "story": "A symbol of transformation and quiet luxury.",
        "sizes": ["Adjustable"],
        "is_best_seller": True,
        "is_curated": True,
        "best_seller_order": 3,
        "curated_order": 3,
    },
    {
        "slug": "love-ring",
        "name": "Love Ring",
        "price_inr": 41860,
        "category": "rings",
        "material": "92.5% sterling silver, hand-set premium stones",
        "description": "The Love Ring — sterling silver designed to symbolize everlasting affection.",
        "story": "A treasured keepsake for meaningful moments.",
        "sizes": ["Adjustable"],
        "is_best_seller": True,
        "best_seller_order": 4,
    },
    {
        "slug": "heart-shaped-earrings",
        "name": "Heart Shaped Earrings",
        "price_inr": 38760,
        "category": "earrings",
        "material": "92.5% sterling silver, gold-toned detailing",
        "description": "Heart Shaped Earrings — delicate sterling silver inspired by modern romance.",
        "story": "Understated romance and quiet luxury.",
        "sizes": [],
        "is_best_seller": True,
        "best_seller_order": 5,
    },
    {
        "slug": "little-bird-earrings",
        "name": "Little Bird Earrings",
        "price_inr": 43780,
        "category": "earrings",
        "material": "92.5% sterling silver, red gemstone detailing",
        "description": "Little Bird Earrings — inspired by freedom and effortless beauty.",
        "story": "Delicate craftsmanship with contemporary luxury.",
        "sizes": [],
        "is_curated": True,
        "curated_order": 4,
    },
    {
        "slug": "mother-baby-earrings",
        "name": "Mother & Baby Earrings",
        "price_inr": 44280,
        "category": "earrings",
        "material": "92.5% sterling silver, gold-plated detailing",
        "description": "Mother & Baby Earrings — inspired by the bond between mother and child.",
        "story": "A keepsake to be remembered across generations.",
        "sizes": [],
        "is_best_seller": True,
        "best_seller_order": 6,
    },
    {
        "slug": "nature-drop-earrings",
        "name": "Nature Drop Earrings",
        "price_inr": 41540,
        "category": "earrings",
        "material": "92.5% sterling silver, gold-toned detailing",
        "description": "Nature Drop Earrings — fluid forms and timeless sophistication.",
        "story": "Quiet sophistication and artisanal beauty.",
        "sizes": [],
        "is_curated": True,
        "curated_order": 5,
    },
    {
        "slug": "infinity-couple-ring",
        "name": "Infinity Couple Ring",
        "price_inr": 45920,
        "category": "rings",
        "material": "92.5% sterling silver, hand-set premium stones",
        "description": "Infinity Couple Ring — inspired by infinite connection.",
        "story": "A meaningful keepsake and sophisticated essential.",
        "sizes": ["Adjustable"],
        "is_curated": True,
        "curated_order": 6,
    },
    {
        "slug": "endless-love-ring",
        "name": "Endless Love Ring",
        "price_inr": 36880,
        "category": "rings",
        "material": "92.5% sterling silver, hand-polished finish",
        "description": "Endless Love Ring — timeless connection in sterling silver.",
        "story": "Understated elegance and emotional beauty.",
        "sizes": ["Adjustable"],
        "is_curated": True,
        "curated_order": 7,
    },
]


async def main() -> None:
    await ensure_categories()
    service = ProductService()
    created: list[str] = []

    for item in DEMO_PRODUCTS:
        payload = {**COMMON, **item}
        product = JewelryProductCreate(**payload)
        saved = await service.upsert_by_slug(product)
        created.append(f"{saved.slug} -> {saved.id}")

    print(f"Seeded {len(created)} demo products into MongoDB ({CATEGORIES[0]['slug']} + rings + necklaces)")
    print("Primary checkout test product: wing-ring")
    for line in created:
        print(f"  {line}")


if __name__ == "__main__":
    asyncio.run(main())
