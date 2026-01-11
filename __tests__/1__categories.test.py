import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.connection import db
from src.services.category_service import CategoryService
from src.models.category import CategoryCreate, Discount, Media


async def test_create_categories():
    await db.connect()
    service = CategoryService()
    
    category1 = CategoryCreate(
        name="Electronics",
        description="Electronic devices and gadgets",
        medias=[Media(url="https://example.com/electronics.jpg", mimetype="image/jpeg", size=1024)],
        discount=Discount(rate=10, type="percentage")
    )
    
    category2 = CategoryCreate(
        name="Clothing",
        description="Apparel and fashion items",
        medias=[Media(url="https://example.com/clothing.jpg", mimetype="image/jpeg", size=1024)],
        discount=Discount(rate=15, type="percentage")
    )
    
    cat1 = await service.create(category1)
    cat2 = await service.create(category2)
    
    print(f"Created category 1: {cat1.id} - {cat1.name}")
    print(f"Created category 2: {cat2.id} - {cat2.name}")
    
    return {
        "electronics_id": str(cat1.id),
        "clothing_id": str(cat2.id)
    }


async def test_update_category_discount():
    await db.connect()
    service = CategoryService()
    
    categories = await service.list()
    if categories:
        category = categories[0]
        updated = await service.update(
            str(category.id),
            {"discount": {"rate": 20, "type": "percentage"}}
        )
        if updated:
            print(f"Updated category {updated.name} discount to {updated.discount.rate}%")
            return str(updated.id)
    return None


if __name__ == "__main__":
    print("=== Creating Categories ===")
    category_ids = asyncio.run(test_create_categories())
    print(f"\nCategory IDs: {category_ids}")
    
    print("\n=== Updating Category Discount ===")
    updated_id = asyncio.run(test_update_category_discount())
    if updated_id:
        print(f"Updated category ID: {updated_id}")

