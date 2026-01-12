import asyncio
import sys
import os
import json
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.connection import db
from src.services.category_service import CategoryService
from src.services.product_service import ProductService
from src.models.category import CategoryCreate, Discount, Media
from src.models.product import ProductCreate, ProductVariant, VariantValue


def parse_mock_data():
    """Parse mock data from the text file and extract all valid product images"""
    mock_data_file = "/home/sourav/Documents/streaming-projects/lowkey-ecom-ui/docs/mock-data.txt"
    
    try:
        with open(mock_data_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract JSON arrays from the file (they're wrapped in backticks)
        json_arrays = []
        all_product_images = []  # Collect all valid product images
        
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('`') and line.endswith('`'):
                json_str = line[1:-1]  # Remove backticks
                try:
                    data = json.loads(json_str)
                    if isinstance(data, list):
                        json_arrays.append(data)
                        # Collect all valid product images
                        for item in data:
                            if isinstance(item, dict):
                                alt_text = item.get('alt', '')
                                image_url = item.get('src', '')
                                if (alt_text and image_url and 
                                    'logo' not in alt_text.lower() and 
                                    'app' not in alt_text.lower() and 
                                    'gokwik' not in alt_text.lower() and 
                                    'banner' not in alt_text.lower() and
                                    'fallback-placeholder' not in image_url):
                                    all_product_images.append({
                                        'name': alt_text,
                                        'image': image_url
                                    })
                except:
                    pass
        
        return json_arrays, all_product_images
    except Exception as e:
        print(f"Error reading mock data: {e}")
        return [], []


def extract_product_info(item):
    """Extract product information from mock data item"""
    if not isinstance(item, dict):
        return None
    
    alt_text = item.get('alt', '')
    image_url = item.get('src', '')
    
    # Skip logos and non-product images
    if 'logo' in alt_text.lower() or 'app' in alt_text.lower() or 'gokwik' in alt_text.lower() or 'banner' in alt_text.lower():
        return None
    
    # Skip placeholder images
    if 'fallback-placeholder' in image_url:
        return None
    
    return {
        'name': alt_text,
        'image': image_url,
        'alt': alt_text
    }


def categorize_product(name):
    """Determine category based on product name"""
    name_lower = name.lower()
    
    # Phone cases
    if any(keyword in name_lower for keyword in ['glass cover', 'phone cover', 'case']):
        return 'Phone Cases & Accessories'
    
    # Women's clothing
    if 'women' in name_lower or "women's" in name_lower:
        if any(keyword in name_lower for keyword in ['jogger', 'track pant', 'cargo']):
            return "Women's Joggers & Pants"
        elif any(keyword in name_lower for keyword in ['hoodie', 'sweatshirt', 'sweater']):
            return "Women's Hoodies & Sweatshirts"
        elif 'jean' in name_lower:
            return "Women's Jeans"
        elif 't-shirt' in name_lower or 'tshirt' in name_lower:
            return "Women's T-shirts"
        else:
            return "Women's Clothing"
    
    # Men's clothing
    if 'men' in name_lower or "men's" in name_lower:
        if any(keyword in name_lower for keyword in ['jogger', 'track pant', 'cargo']):
            return "Men's Joggers & Pants"
        elif any(keyword in name_lower for keyword in ['hoodie', 'sweatshirt', 'sweater']):
            return "Men's Hoodies & Sweatshirts"
        elif 'jean' in name_lower:
            return "Men's Jeans"
        elif 't-shirt' in name_lower or 'tshirt' in name_lower:
            return "Men's T-shirts"
        else:
            return "Men's Clothing"
    
    # Anime collection
    if any(keyword in name_lower for keyword in ['naruto', 'itachi', 'sasuke', 'kakashi']):
        return "Anime Collection"
    
    # Graphic prints
    if 'graphic' in name_lower or 'printed' in name_lower:
        return "Graphic Prints"
    
    # Oversized collection
    if 'oversized' in name_lower:
        return "Oversized Collection"
    
    return 'Other'


def generate_price_from_name(name):
    """Generate realistic prices based on product type"""
    name_lower = name.lower()
    
    if 'phone' in name_lower or 'cover' in name_lower or 'case' in name_lower:
        base_price = 299
        mrp = base_price + 100
    elif 'hoodie' in name_lower or 'sweatshirt' in name_lower or 'sweater' in name_lower:
        base_price = 899
        mrp = base_price + 300
    elif 'jean' in name_lower:
        base_price = 1299
        mrp = base_price + 500
    elif 'jogger' in name_lower or 'pant' in name_lower:
        base_price = 799
        mrp = base_price + 300
    else:  # T-shirts and others
        base_price = 499
        mrp = base_price + 200
    
    return mrp, base_price


async def seed_categories(service: CategoryService):
    """Create categories"""
    categories_data = [
        {
            "name": "Phone Cases & Accessories",
            "description": "Premium phone cases and screen protectors",
            "image": "https://images.bewakoof.com/t640/kakashi-premium-glass-cover-for-realme-11-5g-657000-1733903476-1.jpg",
            "discount": Discount(rate=15, type="percentage")
        },
        {
            "name": "Women's T-shirts",
            "description": "Stylish and comfortable t-shirts for women",
            "image": "https://images.bewakoof.com/t640/women-s-orange-fresh-as-a-daisy-graphic-printed-boyfriend-t-shirt-638829-1738331416-1.jpg",
            "discount": Discount(rate=20, type="percentage")
        },
        {
            "name": "Women's Joggers & Pants",
            "description": "Comfortable joggers and pants for women",
            "image": "https://images.bewakoof.com/t640/women-black-cargo-carpenter-pants-651226-1743757375-1.jpg",
            "discount": Discount(rate=25, type="percentage")
        },
        {
            "name": "Women's Hoodies & Sweatshirts",
            "description": "Cozy hoodies and sweatshirts for women",
            "image": "https://images.bewakoof.com/t640/women-s-black-cosmic-culture-graphic-printed-oversized-crop-hoodies-694460-1762435991-1.jpg",
            "discount": Discount(rate=30, type="percentage")
        },
        {
            "name": "Women's Jeans",
            "description": "Trendy jeans for women",
            "image": "https://images.bewakoof.com/t640/women-s-blue-straight-fit-jeans-662194-1758194378-1.jpg",
            "discount": Discount(rate=20, type="percentage")
        },
        {
            "name": "Men's T-shirts",
            "description": "Cool and comfortable t-shirts for men",
            "image": "https://images.bewakoof.com/t640/men-s-maroon-dead-pool-jersey-graphic-printed-oversized-t-shirt-580072-1761658537-1.jpg",
            "discount": Discount(rate=20, type="percentage")
        },
        {
            "name": "Men's Joggers & Pants",
            "description": "Comfortable joggers and pants for men",
            "image": "https://images.bewakoof.com/t640/men-s-black-oversized-joggers-646471-1735812970-1.jpg",
            "discount": Discount(rate=25, type="percentage")
        },
        {
            "name": "Men's Hoodies & Sweatshirts",
            "description": "Stylish hoodies and sweatshirts for men",
            "image": "https://images.bewakoof.com/t640/men-s-black-oversized-hoodies-368338-1732118117-1.jpg",
            "discount": Discount(rate=30, type="percentage")
        },
        {
            "name": "Men's Jeans",
            "description": "Classic and trendy jeans for men",
            "image": "https://images.bewakoof.com/t640/women-s-blue-straight-fit-jeans-662194-1758194378-1.jpg",
            "discount": Discount(rate=20, type="percentage")
        },
        {
            "name": "Electronics",
            "description": "Electronic devices and gadgets",
            "image": "https://images.unsplash.com/photo-1498049794561-7780e7231661?w=800",
            "discount": Discount(rate=10, type="percentage")
        },
        {
            "name": "Footwear",
            "description": "Shoes and sneakers for all occasions",
            "image": "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=800",
            "discount": Discount(rate=25, type="percentage")
        },
        {
            "name": "Accessories",
            "description": "Fashion accessories and add-ons",
            "image": "https://images.unsplash.com/photo-1594223274512-ad4803739b7c?w=800",
            "discount": Discount(rate=15, type="percentage")
        },
        {
            "name": "Home & Living",
            "description": "Home decor and living essentials",
            "image": "https://images.unsplash.com/photo-1586023492125-27b2c045efd7?w=800",
            "discount": Discount(rate=20, type="percentage")
        },
        {
            "name": "Sports & Fitness",
            "description": "Sports equipment and fitness gear",
            "image": "https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=800",
            "discount": Discount(rate=15, type="percentage")
        },
        {
            "name": "Beauty & Personal Care",
            "description": "Beauty products and personal care items",
            "image": "https://images.unsplash.com/photo-1596462502278-27bfdc403348?w=800",
            "discount": Discount(rate=20, type="percentage")
        },
        {
            "name": "Anime Collection",
            "description": "Anime-themed products and merchandise",
            "image": "https://images.bewakoof.com/t640/kakashi-premium-glass-cover-for-realme-11-5g-657000-1733903476-1.jpg",
            "discount": Discount(rate=20, type="percentage")
        },
        {
            "name": "Graphic Prints",
            "description": "Graphic printed clothing and accessories",
            "image": "https://images.bewakoof.com/t640/women-s-orange-fresh-as-a-daisy-graphic-printed-boyfriend-t-shirt-638829-1738331416-1.jpg",
            "discount": Discount(rate=25, type="percentage")
        },
        {
            "name": "Oversized Collection",
            "description": "Oversized and relaxed fit clothing",
            "image": "https://images.bewakoof.com/t640/women-s-pink-no-worries-graphic-printed-oversized-t-shirt-655171-1736330167-1.jpg",
            "discount": Discount(rate=22, type="percentage")
        },
    ]
    
    category_map = {}
    
    for cat_data in categories_data:
        category = CategoryCreate(
            name=cat_data["name"],
            description=cat_data["description"],
            medias=[Media(url=cat_data["image"], mimetype="image/jpeg", size=0)],
            discount=cat_data["discount"]
        )
        
        created = await service.create(category)
        category_map[cat_data["name"]] = str(created.id)
        print(f"✓ Created category: {cat_data['name']} (ID: {created.id})")
    
    return category_map


def get_similar_images(all_images, current_product, category_name, max_images=3):
    """Get similar product images from mock data for additional medias"""
    similar_images = []
    name_lower = current_product['name'].lower()
    
    for img in all_images:
        if img['image'] == current_product['image']:
            continue
        
        img_name_lower = img['name'].lower()
        
        # Match by category keywords
        if category_name == "Phone Cases & Accessories":
            if any(kw in img_name_lower for kw in ['cover', 'case', 'glass']):
                similar_images.append(img['image'])
        elif "T-shirt" in category_name:
            if 't-shirt' in img_name_lower or 'tshirt' in img_name_lower:
                similar_images.append(img['image'])
        elif "Joggers" in category_name or "Pants" in category_name:
            if any(kw in img_name_lower for kw in ['jogger', 'pant', 'cargo', 'track']):
                similar_images.append(img['image'])
        elif "Hoodies" in category_name or "Sweatshirts" in category_name:
            if any(kw in img_name_lower for kw in ['hoodie', 'sweatshirt', 'sweater']):
                similar_images.append(img['image'])
        elif "Jeans" in category_name:
            if 'jean' in img_name_lower:
                similar_images.append(img['image'])
        
        if len(similar_images) >= max_images:
            break
    
    return similar_images


async def seed_products(product_service: ProductService, category_map: dict, mock_data_arrays: list, all_product_images: list):
    """Create products from mock data"""
    products_created = 0
    import random
    
    for data_array in mock_data_arrays:
        for item in data_array:
            product_info = extract_product_info(item)
            if not product_info:
                continue
            
            category_name = categorize_product(product_info['name'])
            category_id = category_map.get(category_name)
            
            if not category_id:
                continue
            
            mrp, selling_price = generate_price_from_name(product_info['name'])
            
            # Extract brand from name or use default
            brand = "Bewakoof"
            name_lower = product_info['name'].lower()
            if any(kw in product_info['name'] for kw in ["Naruto", "Itachi", "Sasuke", "Kakashi"]):
                brand = "Anime Collection"
            elif any(kw in product_info['name'] for kw in ["NASA", "Space", "Astronaut"]):
                brand = "Space Collection"
            elif any(kw in product_info['name'] for kw in ["Batman", "Joker", "Deadpool", "Spider"]):
                brand = "DC Comics"
            elif "Friends" in product_info['name']:
                brand = "Friends Collection"
            elif "Minion" in product_info['name']:
                brand = "Despicable Me"
            
            # Generate tags from alt text
            tags = []
            if 'graphic' in name_lower or 'printed' in name_lower:
                tags.append('graphic')
            if 'oversized' in name_lower:
                tags.append('oversized')
            if 'boyfriend' in name_lower:
                tags.append('boyfriend-fit')
            if 'premium' in name_lower:
                tags.append('premium')
            if 'all over' in name_lower or 'all-over' in name_lower:
                tags.append('all-over-print')
            if 'striped' in name_lower:
                tags.append('striped')
            if 'cargo' in name_lower:
                tags.append('cargo')
            if 'baggy' in name_lower or 'wide leg' in name_lower:
                tags.append('baggy')
            
            # Create product variants (size for clothing, color for phone cases)
            variants = []
            if 'phone' in name_lower or 'cover' in name_lower:
                variants = [
                    ProductVariant(
                        variant_name="Device Model",
                        variant_values=[
                            VariantValue(label="Realme 11 5G", active=True),
                            VariantValue(label="iPhone 15", active=True),
                            VariantValue(label="Samsung S24", active=True),
                        ]
                    )
                ]
            else:
                # Extract color from name if available
                colors = []
                color_keywords = ['black', 'white', 'blue', 'red', 'green', 'yellow', 'pink', 'purple', 'orange', 'brown', 'grey', 'gray', 'beige', 'maroon', 'navy']
                for color in color_keywords:
                    if color in name_lower:
                        colors.append(color.capitalize())
                
                if not colors:
                    colors = ["Default"]
                
                variants = [
                    ProductVariant(
                        variant_name="Size",
                        variant_values=[
                            VariantValue(label="S", active=True),
                            VariantValue(label="M", active=True),
                            VariantValue(label="L", active=True),
                            VariantValue(label="XL", active=True),
                        ]
                    ),
                    ProductVariant(
                        variant_name="Color",
                        variant_values=[VariantValue(label=color, active=True) for color in colors[:3]]
                    )
                ]
            
            # Generate multiple medias (3-4 images per product) using mock data images
            medias = [Media(url=product_info['image'], mimetype="image/jpeg", size=0)]
            
            # Get similar images from mock data
            similar_images = get_similar_images(all_product_images, product_info, category_name, max_images=3)
            
            # Add 2-3 additional images from similar products
            num_additional = random.randint(2, 3)
            for img_url in similar_images[:num_additional]:
                medias.append(Media(url=img_url, mimetype="image/jpeg", size=0))
            
            product = ProductCreate(
                name=product_info['name'],
                brand=brand,
                categories=[category_id],
                product_description=f"Premium quality {product_info['name']}. Made with high-quality materials for comfort and style.",
                mrp_price=mrp,
                selling_price=selling_price,
                tags=tags,
                medias=medias,
                features=[
                    "Premium Quality",
                    "Comfortable Fit",
                    "Durable Material",
                    "Easy Care"
                ],
                active=True,
                product_variants=variants
            )
            
            try:
                created = await product_service.create(product)
                products_created += 1
                if products_created % 10 == 0:
                    print(f"✓ Created {products_created} products...")
            except Exception as e:
                print(f"✗ Error creating product {product_info['name']}: {e}")
    
    return products_created


async def main():
    """Main seeding function"""
    print("=" * 60)
    print("Starting Database Seeding")
    print("=" * 60)
    
    await db.connect()
    
    category_service = CategoryService()
    product_service = ProductService()
    
    # Parse mock data
    print("\n[1/3] Parsing mock data...")
    mock_data_arrays, all_product_images = parse_mock_data()
    print(f"✓ Found {len(mock_data_arrays)} data arrays")
    print(f"✓ Extracted {len(all_product_images)} valid product images")
    
    # Create categories
    print("\n[2/3] Creating categories...")
    category_map = await seed_categories(category_service)
    print(f"✓ Created {len(category_map)} categories")
    
    # Create products
    print("\n[3/3] Creating products...")
    products_created = await seed_products(product_service, category_map, mock_data_arrays, all_product_images)
    print(f"✓ Created {products_created} products")
    
    print("\n" + "=" * 60)
    print("Seeding Complete!")
    print(f"Categories: {len(category_map)}")
    print(f"Products: {products_created}")
    print("=" * 60)
    
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
