import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.connection import db
from src.services.product_service import ProductService
from src.services.category_service import CategoryService
from src.models.product import ProductCreate, Media


async def get_category_ids():
    await db.connect()
    service = CategoryService()
    categories = await service.list()
    if len(categories) >= 2:
        return {
            "electronics_id": str(categories[0].id),
            "clothing_id": str(categories[1].id)
        }
    return {"electronics_id": None, "clothing_id": None}


async def test_create_products():
    await db.connect()
    service = ProductService()
    category_ids = await get_category_ids()
    
    electronics_id = category_ids.get("electronics_id")
    clothing_id = category_ids.get("clothing_id")
    
    product1 = ProductCreate(
        name="iPhone 15 Pro",
        brand="Apple",
        categories=[electronics_id] if electronics_id else [],
        product_description="Latest iPhone with advanced features",
        mrp_price=99999.0,
        selling_price=89999.0,
        tags=["smartphone", "apple", "premium"],
        medias=[Media(url="https://example.com/iphone.jpg", mimetype="image/jpeg", size=2048)],
        features=["A17 Pro chip", "48MP camera", "Titanium design"]
    )
    
    product2 = ProductCreate(
        name="Samsung Galaxy S24",
        brand="Samsung",
        categories=[electronics_id] if electronics_id else [],
        product_description="Flagship Android smartphone",
        mrp_price=79999.0,
        selling_price=69999.0,
        tags=["smartphone", "samsung", "android"],
        medias=[Media(url="https://example.com/galaxy.jpg", mimetype="image/jpeg", size=2048)],
        features=["Snapdragon 8 Gen 3", "200MP camera", "AI features"]
    )
    
    product3 = ProductCreate(
        name="Nike Air Max",
        brand="Nike",
        categories=[clothing_id] if clothing_id else [],
        product_description="Classic running shoes",
        mrp_price=12999.0,
        selling_price=10999.0,
        tags=["shoes", "nike", "sports"],
        medias=[Media(url="https://example.com/nike.jpg", mimetype="image/jpeg", size=2048)],
        features=["Air cushioning", "Breathable mesh", "Durable sole"]
    )
    
    p1 = await service.create(product1)
    p2 = await service.create(product2)
    p3 = await service.create(product3)
    
    print(f"Created product 1: {p1.id} - {p1.name} (Category: {p1.categories})")
    print(f"Created product 2: {p2.id} - {p2.name} (Category: {p2.categories})")
    print(f"Created product 3: {p3.id} - {p3.name} (Category: {p3.categories})")
    
    return {
        "product1_id": str(p1.id),
        "product2_id": str(p2.id),
        "product3_id": str(p3.id)
    }


async def test_list_products_with_categories():
    await db.connect()
    service = ProductService()
    
    products = await service.list(include_categories=True)
    
    print("\n=== Products with Category Details ===")
    for product in products:
        print(f"\nProduct: {product.get('name')}")
        print(f"Brand: {product.get('brand')}")
        print(f"Price: ₹{product.get('selling_price')}")
        if product.get('category_details'):
            print("Categories:")
            for cat in product.get('category_details', []):
                print(f"  - {cat.get('name')}: {cat.get('discount', {}).get('rate')}% discount")
        else:
            print("No categories")
    
    return products


async def test_search_products():
    await db.connect()
    service = ProductService()
    
    print("\n=== Searching for 'iPhone' ===")
    results = await service.search("iPhone", include_categories=True)
    
    for product in results:
        print(f"Found: {product.get('name')} - {product.get('brand')}")
        if product.get('category_details'):
            for cat in product.get('category_details', []):
                print(f"  Category: {cat.get('name')} ({cat.get('discount', {}).get('rate')}% off)")
    
    return results


if __name__ == "__main__":
    print("=== Creating Products ===")
    product_ids = asyncio.run(test_create_products())
    print(f"\nProduct IDs: {product_ids}")
    
    asyncio.run(test_list_products_with_categories())
    asyncio.run(test_search_products())

