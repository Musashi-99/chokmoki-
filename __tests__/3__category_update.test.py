import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.connection import db
from src.services.category_service import CategoryService
from src.services.product_service import ProductService


async def test_update_category_and_verify_products():
    await db.connect()
    category_service = CategoryService()
    product_service = ProductService()
    
    categories = await category_service.list()
    if not categories:
        print("No categories found. Run 1__categories.test.py first.")
        return
    
    target_category = categories[0]
    print(f"\n=== Updating Category: {target_category.name} ===")
    print(f"Current discount: {target_category.discount.rate}%")
    
    updated = await category_service.update(
        str(target_category.id),
        {"discount": {"rate": 25, "type": "percentage"}}
    )
    
    if updated:
        print(f"Updated discount to: {updated.discount.rate}%")
        
        print("\n=== Verifying Products Show Updated Category ===")
        products = await product_service.list(include_categories=True)
        
        for product in products:
            if product.get('category_details'):
                for cat in product.get('category_details', []):
                    if str(cat.get('_id')) == str(target_category.id):
                        print(f"\nProduct: {product.get('name')}")
                        print(f"Category: {cat.get('name')}")
                        print(f"Discount: {cat.get('discount', {}).get('rate')}%")
                        if cat.get('discount', {}).get('rate') == 25:
                            print("✓ Category update reflected in product!")
                        else:
                            print("✗ Category update NOT reflected in product")


if __name__ == "__main__":
    asyncio.run(test_update_category_and_verify_products())

