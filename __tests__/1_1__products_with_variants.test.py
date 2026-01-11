import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.connection import db
from src.services.product_service import ProductService
from src.services.category_service import CategoryService
from src.models.product import ProductCreate, Media, ProductVariant, VariantValue


async def get_category_id():
    service = CategoryService()
    categories = await service.list()
    if categories:
        return str(categories[0].id)
    return None


async def test_create_product_without_variants():
    service = ProductService()
    category_id = await get_category_id()
    
    print("\n=== Test 1: Creating Product WITHOUT Variants (should get default variant) ===")
    
    product = ProductCreate(
        name="Simple T-Shirt",
        brand="Basic Brand",
        categories=[category_id] if category_id else [],
        product_description="A simple t-shirt without variants",
        mrp_price=999.0,
        selling_price=799.0,
        tags=["clothing", "tshirt"],
        medias=[Media(url="https://example.com/tshirt.jpg", mimetype="image/jpeg", size=1024)],
        features=["100% Cotton", "Machine washable"]
    )
    
    created = await service.create(product)
    
    print(f"✓ Product created: {created.name} (ID: {created.id})")
    print(f"  Variants count: {len(created.product_variants)}")
    
    if created.product_variants:
        for variant in created.product_variants:
            print(f"  Variant: {variant.variant_name}")
            for value in variant.variant_values:
                print(f"    - {value.label} (active: {value.active})")
    
    assert len(created.product_variants) > 0, "Product should have at least one variant (default)"
    assert created.product_variants[0].variant_name == "default", "First variant should be 'default'"
    
    return str(created.id)


async def test_create_product_with_size_variants():
    service = ProductService()
    category_id = await get_category_id()
    
    print("\n=== Test 2: Creating Product WITH Size Variants ===")
    
    size_variants = ProductVariant(
        variant_name="size",
        variant_values=[
            VariantValue(label="S", active=True),
            VariantValue(label="M", active=True),
            VariantValue(label="L", active=True),
            VariantValue(label="XL", active=False)
        ]
    )
    
    product = ProductCreate(
        name="Premium Hoodie",
        brand="Fashion Co",
        categories=[category_id] if category_id else [],
        product_description="Premium hoodie with size variants",
        mrp_price=2999.0,
        selling_price=2499.0,
        tags=["clothing", "hoodie", "premium"],
        medias=[Media(url="https://example.com/hoodie.jpg", mimetype="image/jpeg", size=2048)],
        features=["Fleece lining", "Kangaroo pocket", "Drawstring hood"],
        product_variants=[size_variants]
    )
    
    created = await service.create(product)
    
    print(f"✓ Product created: {created.name} (ID: {created.id})")
    print(f"  Variants count: {len(created.product_variants)}")
    
    for variant in created.product_variants:
        print(f"  Variant: {variant.variant_name}")
        for value in variant.variant_values:
            status = "✓" if value.active else "✗"
            print(f"    {status} {value.label} (active: {value.active})")
    
    assert len(created.product_variants) == 1, "Should have exactly 1 variant"
    assert created.product_variants[0].variant_name == "size", "Variant name should be 'size'"
    assert len(created.product_variants[0].variant_values) == 4, "Should have 4 size values"
    
    return str(created.id)


async def test_create_product_with_multiple_variants():
    service = ProductService()
    category_id = await get_category_id()
    
    print("\n=== Test 3: Creating Product WITH Multiple Variants (Size + Color) ===")
    
    size_variant = ProductVariant(
        variant_name="size",
        variant_values=[
            VariantValue(label="S", active=True),
            VariantValue(label="M", active=True),
            VariantValue(label="L", active=True)
        ]
    )
    
    color_variant = ProductVariant(
        variant_name="color",
        variant_values=[
            VariantValue(label="Blue", active=True),
            VariantValue(label="Green", active=True),
            VariantValue(label="Red", active=False)
        ]
    )
    
    product = ProductCreate(
        name="Designer Jeans",
        brand="Denim Co",
        categories=[category_id] if category_id else [],
        product_description="Designer jeans with size and color variants",
        mrp_price=4999.0,
        selling_price=3999.0,
        tags=["clothing", "jeans", "designer"],
        medias=[
            Media(url="https://example.com/jeans-blue.jpg", mimetype="image/jpeg", size=2048),
            Media(url="https://example.com/jeans-green.jpg", mimetype="image/jpeg", size=2048)
        ],
        features=["Stretch fabric", "5-pocket design", "Pre-washed"],
        product_variants=[size_variant, color_variant]
    )
    
    created = await service.create(product)
    
    print(f"✓ Product created: {created.name} (ID: {created.id})")
    print(f"  Variants count: {len(created.product_variants)}")
    
    for variant in created.product_variants:
        print(f"  Variant: {variant.variant_name}")
        for value in variant.variant_values:
            status = "✓" if value.active else "✗"
            print(f"    {status} {value.label} (active: {value.active})")
    
    assert len(created.product_variants) == 2, "Should have exactly 2 variants"
    assert any(v.variant_name == "size" for v in created.product_variants), "Should have size variant"
    assert any(v.variant_name == "color" for v in created.product_variants), "Should have color variant"
    
    return str(created.id)


async def test_retrieve_product_and_verify_variants():
    service = ProductService()
    
    print("\n=== Test 4: Retrieving Products and Verifying Variants ===")
    
    products = await service.list(include_categories=False)
    
    print(f"Found {len(products)} products")
    
    for product in products:
        print(f"\nProduct: {product.get('name')}")
        variants = product.get('product_variants', [])
        print(f"  Variants: {len(variants)}")
        
        for variant in variants:
            variant_name = variant.get('variant_name', 'unknown')
            values = variant.get('variant_values', [])
            active_count = sum(1 for v in values if v.get('active', False))
            print(f"    - {variant_name}: {len(values)} values ({active_count} active)")
            for value in values:
                label = value.get('label', 'unknown')
                active = value.get('active', False)
                status = "✓" if active else "✗"
                print(f"      {status} {label}")


async def test_search_products_with_variants():
    service = ProductService()
    
    print("\n=== Test 5: Searching Products and Checking Variants ===")
    
    results = await service.search("Jeans", include_categories=False)
    
    print(f"Found {len(results)} products matching 'Jeans'")
    
    for product in results:
        print(f"\nProduct: {product.get('name')}")
        variants = product.get('product_variants', [])
        if variants:
            print("  Variants:")
            for variant in variants:
                print(f"    {variant.get('variant_name')}: {len(variant.get('variant_values', []))} options")


async def run_all_tests():
    print("=" * 60)
    print("PRODUCT VARIANTS TEST SUITE")
    print("=" * 60)
    
    await db.connect()
    
    try:
        product1_id = await test_create_product_without_variants()
        product2_id = await test_create_product_with_size_variants()
        product3_id = await test_create_product_with_multiple_variants()
        
        print(f"\n✓ Created products:")
        print(f"  - Product 1 (no variants): {product1_id}")
        print(f"  - Product 2 (size variants): {product2_id}")
        print(f"  - Product 3 (size + color): {product3_id}")
        
        await test_retrieve_product_and_verify_variants()
        await test_search_products_with_variants()
        
        print("\n" + "=" * 60)
        print("ALL TESTS COMPLETED")
        print("=" * 60)
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(run_all_tests())

