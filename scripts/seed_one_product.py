"""Seed one random jewelry product into the local chokmoki database."""
import asyncio
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.database.connection import db
from src.models.category import JewelryCategoryCreate
from src.models.product import JewelryProductCreate
from src.services.category_service import CategoryService
from src.services.product_service import ProductService
from src.services.r2_service import R2Service

NAMES = [
    "Gilded Vine Filigree Drop Earrings",
    "Butterfly Whisper Ring",
    "Celestial Crescent Pendant",
    "Lotus Bloom Stud Earrings",
    "Moonlit Serpent Chain",
]
COLLECTIONS = ["Chokmoki Archive", "Studio Edit", "Evening Light", "Heritage Line"]
MATERIALS = [
    "92.5% sterling silver with 22k gold vermeil accents",
    "Solid sterling silver with hand-set cubic zirconia",
    "Oxidised sterling silver with brushed finish",
]
CATEGORIES = [
    {
        "slug": "earrings",
        "name": "Earrings",
        "tagline": "Sculpted light for every gesture",
        "banner": "https://images.unsplash.com/photo-1535632066927-ab7c9ab60908?w=1600&q=80",
        "thumbnail": "https://images.unsplash.com/photo-1535632066927-ab7c9ab60908?w=600&q=80",
        "description": "Handcrafted earrings shaped for quiet luxury.",
        "sort_order": 1,
    },
    {
        "slug": "rings",
        "name": "Rings",
        "tagline": "Symbols you carry close",
        "banner": "https://images.unsplash.com/photo-1605100804763-247f67b3557e?w=1600&q=80",
        "thumbnail": "https://images.unsplash.com/photo-1605100804763-247f67b3557e?w=600&q=80",
        "description": "Adjustable and statement rings in sterling silver.",
        "sort_order": 2,
    },
    {
        "slug": "necklaces",
        "name": "Necklaces",
        "tagline": "Lines that frame the collarbone",
        "banner": "https://images.unsplash.com/photo-1599643478518-a784e5dc4c8f?w=1600&q=80",
        "thumbnail": "https://images.unsplash.com/photo-1599643478518-a784e5dc4c8f?w=600&q=80",
        "description": "Pendants and chains finished in our Kolkata studio.",
        "sort_order": 3,
    },
]

IMAGE_URLS = {
    "earrings": "https://images.unsplash.com/photo-1535632066927-ab7c9ab60908?w=1200&q=85",
    "rings": "https://images.unsplash.com/photo-1605100804763-247f67b3557e?w=1200&q=85",
    "necklaces": "https://images.unsplash.com/photo-1599643478518-a784e5dc4c8f?w=1200&q=85",
}


def slugify(name: str) -> str:
    return (
        name.lower()
        .replace("&", "and")
        .replace("'", "")
        .replace(",", "")
        .replace("—", "-")
        .replace("–", "-")
        .replace(" ", "-")
    )


async def ensure_categories() -> None:
    service = CategoryService()
    for cat in CATEGORIES:
        if await service.get_by_slug(cat["slug"]):
            continue
        await service.create(JewelryCategoryCreate(**cat))


async def upload_image(category: str) -> str:
    url = IMAGE_URLS[category]
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        image_bytes = response.content

    r2 = R2Service()
    uploaded = await r2.upload_file(image_bytes, "jpg", "image/jpeg", folder="products")
    if uploaded:
        return uploaded
    return url


async def main() -> None:
    category = random.choice(["earrings", "rings", "necklaces"])
    name = random.choice(NAMES)
    slug = f"{slugify(name)}-{random.randint(100, 999)}"
    price_inr = random.choice([12990, 18750, 24600, 31800, 39760, 45200])
    collection = random.choice(COLLECTIONS)
    material = random.choice(MATERIALS)

    await ensure_categories()
    thumbnail = await upload_image(category)
    gallery = [thumbnail]

    product = JewelryProductCreate(
        slug=slug,
        name=name,
        price_inr=price_inr,
        category=category,
        collection=collection,
        thumbnail=thumbnail,
        gallery=gallery,
        material=material,
        craftsmanship=(
            "Handcrafted in Kolkata with traditional filigree techniques, "
            "each curve finished by hand for a soft luminous surface."
        ),
        shipping_details="Complimentary Pan-India shipping. Express delivery in 3–5 business days.",
        care_guide="Store dry, polish gently with a soft cloth, avoid perfume and moisture.",
        returns_policy="14-day returns on unworn pieces in original packaging.",
        authenticity_details="Certified 92.5% sterling silver with studio authenticity card.",
        description=(
            f"{name} from the {collection} collection — a sterling silver piece "
            f"designed for everyday elegance with artisan detailing."
        ),
        story=f"Inspired by Kolkata light and unhurried craft, the {name} was shaped for women who wear meaning softly.",
        sizes=random.sample(["XS", "S", "M", "L", "Adjustable"], k=2),
        is_best_seller=random.choice([True, False]),
        is_curated=random.choice([True, False]),
        best_seller_order=random.randint(1, 20),
        curated_order=random.randint(1, 20),
        weight_grams=round(random.uniform(3.5, 18.0), 1),
        purity="92.5% Sterling Silver",
        stock_status="in_stock",
        active=True,
    )

    created = await ProductService().create(product)
    print(f"Created product: {created.name}")
    print(f"Slug: {created.slug}")
    print(f"ID: {created.id}")
    print(f"Image: {created.thumbnail}")
    print(f"Price: ₹{created.price_inr:,}")


if __name__ == "__main__":
    asyncio.run(main())
