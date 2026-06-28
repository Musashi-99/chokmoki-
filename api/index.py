from fastapi import FastAPI, HTTPException, Request, Header, Depends, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
from typing import Dict, Any, Optional, List
from contextlib import asynccontextmanager
from bson import ObjectId
from datetime import datetime, timezone, timedelta
import json
import sys
import platform
import asyncio
import os

from dotenv import load_dotenv

load_dotenv(override=False)

# Optional imports – do NOT crash boot
try:
    from src.database.connection import db
    from src.database.redis_connection import redis_client
    from src.cqrs.router import CQRSRouter
    from src.services.razorpay_service import RazorpayService
    from src.services.order_service import OrderService
    from src.services.telegram_service import TelegramService
    from src.plugins.logger import logger
    from src.config import settings
    from src.plugins.rate_limit import RateLimitMiddleware
    from src.services.product_service import ProductService
    from src.services.category_service import CategoryService
    from src.models.product import JewelryProductCreate
    from src.models.category import JewelryCategoryCreate
    from src.models.order import OrderCreateInput, OrderStatus
    from src.services.admin_auth_service import AdminAuthService
    from src.services.r2_service import R2Service
    from src.utils.upload_validation import UploadValidationError, validate_upload
    from src.models.testimonial import TestimonialCreate
    from src.models.hero_config import HeroConfigCreate
    from src.services.testimonial_service import TestimonialService
    from src.services.hero_config_service import HeroConfigService
    from src.models.site_asset import SiteAssetCreate
    from src.models.faq_item import FAQItemCreate
    from src.models.collection_slide import CollectionSlideCreate
    from src.services.site_asset_service import SiteAssetService
    from src.services.faq_item_service import FAQItemService
    from src.services.collection_slide_service import CollectionSlideService
    from src.services.studio_settings_service import StudioSettingsService
    from src.services.shop_page_settings_service import ShopPageSettingsService
    from src.services.policy_content_service import PolicyContentService
    from src.models.studio_settings import StudioSettingsUpdate
    from src.models.shop_page_settings import ShopPageSettingsUpdate
    from src.models.policy_content import PolicyPageMetaUpdate, PolicySectionCreate
    from src.services.home_page_settings_service import HomePageSettingsService
    from src.services.story_page_settings_service import StoryPageSettingsService
    from src.services.blog_service import BlogService
    from src.services.inbox_service import InboxService
    from src.services.navigation_settings_service import NavigationSettingsService
    from src.services.contact_page_settings_service import ContactPageSettingsService
    from src.services.history_page_settings_service import HistoryPageSettingsService
    from src.services.product_page_settings_service import ProductPageSettingsService
    from src.models.home_page_settings import HomePageSettingsUpdate
    from src.models.story_page_settings import StoryPageSettingsUpdate
    from src.models.blog_post import BlogPostCreate, JournalPageSettingsUpdate
    from src.models.navigation_settings import NavigationSettingsUpdate
    from src.models.contact_page_settings import ContactPageSettingsUpdate
    from src.models.history_page_settings import HistoryPageSettingsUpdate
    from src.models.product_page_settings import ProductPageSettingsUpdate
    from src.models.inbox import ContactSubmissionCreate, NewsletterSubscribeCreate
    from src.services.cache_service import cache
except Exception as e:
    print(f"Import error: {e}", file=sys.stderr)
    db = None
    redis_client = None
    CQRSRouter = None
    RazorpayService = None
    OrderService = None
    TelegramService = None
    logger = None
    settings = None
    RateLimitMiddleware = None
    ProductService = None
    CategoryService = None
    JewelryProductCreate = None
    JewelryCategoryCreate = None
    OrderCreateInput = None
    AdminAuthService = None
    R2Service = None
    TestimonialCreate = None
    HeroConfigCreate = None
    TestimonialService = None
    HeroConfigService = None
    SiteAssetCreate = None
    FAQItemCreate = None
    CollectionSlideCreate = None
    SiteAssetService = None
    FAQItemService = None
    CollectionSlideService = None
    StudioSettingsService = None
    ShopPageSettingsService = None
    PolicyContentService = None
    StudioSettingsUpdate = None
    ShopPageSettingsUpdate = None
    PolicyPageMetaUpdate = None
    PolicySectionCreate = None
    HomePageSettingsService = None
    StoryPageSettingsService = None
    BlogService = None
    InboxService = None
    HomePageSettingsUpdate = None
    StoryPageSettingsUpdate = None
    BlogPostCreate = None
    JournalPageSettingsUpdate = None
    NavigationSettingsService = None
    ContactPageSettingsService = None
    HistoryPageSettingsService = None
    ProductPageSettingsService = None
    NavigationSettingsUpdate = None
    ContactPageSettingsUpdate = None
    HistoryPageSettingsUpdate = None
    ProductPageSettingsUpdate = None
    ContactSubmissionCreate = None
    NewsletterSubscribeCreate = None
    cache = None


class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            # Mongo stores naive UTC; suffix Z so clients bucket IST correctly.
            s = obj.isoformat()
            return s if obj.tzinfo is not None else f"{s}Z"
        return super().default(obj)


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, cls=JSONEncoder)


def _json_response_content(obj: Any) -> Any:
    return json.loads(_json_dumps(obj))


class APIRequest(BaseModel):
    type: str
    operation: str
    params: Dict[str, Any] = {}
    adminKey: Optional[str] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage database and Redis connections lifecycle"""
    try:
        if db:
            await db.connect()
            if OrderService is not None:
                try:
                    await OrderService().ensure_indexes()
                except Exception as idx_err:
                    if logger:
                        logger.warning(f"Order index setup skipped: {idx_err}")
        if redis_client:
            await redis_client.connect()
        # Ensure the R2 media bucket exists for dynamic asset hosting
        if R2Service is not None:
            try:
                R2Service().ensure_bucket()
            except Exception as r2_err:
                if logger:
                    logger.warning(f"R2 bucket check skipped: {r2_err}")
    except Exception as e:
        if logger:
            logger.error(f"Startup connection error: {e}")
        print(f"Startup connection error: {e}", file=sys.stderr)
    
    yield
    
    try:
        if db:
            await db.close()
        if redis_client:
            await redis_client.close()
    except Exception as e:
        if logger:
            logger.error(f"Shutdown connection error: {e}")
        print(f"Shutdown connection error: {e}", file=sys.stderr)


# Export THIS ONLY
app = FastAPI(lifespan=lifespan)


if RateLimitMiddleware:
    app.add_middleware(RateLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========== REST API Endpoints for Frontend ==========

async def _cache_products_key(category, search, sort, skip, limit, is_best_seller=None, is_curated=None):
    return (
        f"chokmoki:products:{category or 'all'}:{search or 'all'}:{sort or 'default'}"
        f":bs{is_best_seller}:cur{is_curated}:{skip}:{limit}"
    )


@app.get("/api/products")
async def api_list_products(
    category: Optional[str] = None,
    search: Optional[str] = None,
    sort: Optional[str] = None,
    is_best_seller: Optional[bool] = None,
    is_curated: Optional[bool] = None,
    skip: int = 0,
    limit: int = 50,
):
    """List products with optional filtering (cached)"""
    if ProductService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    cache_key = await _cache_products_key(
        category, search, sort, skip, limit, is_best_seller, is_curated
    )
    if cache:
        cached = await cache.get(cache_key)
        if cached:
            return JSONResponse(content=json.loads(cached))
    
    service = ProductService()
    products = await service.list(
        skip=skip, limit=limit, active=True,
        category=category, sort=sort, search=search,
        is_best_seller=is_best_seller, is_curated=is_curated,
    )
    total = await service.count(
        active=True, category=category, search=search,
        is_best_seller=is_best_seller, is_curated=is_curated,
    )
    result = {"data": products, "count": total}
    
    if cache:
        await cache.set(cache_key, _json_dumps(result), 300)
    
    return JSONResponse(content=_json_response_content(result))


@app.get("/api/products/{slug}")
async def api_get_product(slug: str):
    """Get a single product by slug"""
    if ProductService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    cache_key = f"chokmoki:product:{slug}"
    if cache:
        cached = await cache.get(cache_key)
        if cached:
            return JSONResponse(content=json.loads(cached))
    
    service = ProductService()
    product = await service.get_by_slug(slug)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    result = json.loads(json.dumps(
        product.model_dump(by_alias=True),
        cls=JSONEncoder
    ))
    if cache:
        await cache.set(cache_key, _json_dumps(result), 300)
    
    return JSONResponse(content=result)


@app.get("/api/categories")
async def api_list_categories():
    """List all active categories (cached)"""
    if CategoryService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    cache_key = "chokmoki:categories"
    if cache:
        cached = await cache.get(cache_key)
        if cached:
            return JSONResponse(content=json.loads(cached))
    
    service = CategoryService()
    categories = await service.list(active=True)
    total = await service.count(active=True)
    result = {
        "data": [cat.model_dump(by_alias=True) for cat in categories],
        "count": total
    }
    
    if cache:
        await cache.set(cache_key, _json_dumps(result), 600)
    
    return JSONResponse(content=_json_response_content(result))


@app.get("/api/categories/{slug}")
async def api_get_category(slug: str):
    """Get a single category by slug"""
    if CategoryService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    service = CategoryService()
    category = await service.get_by_slug(slug)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    return JSONResponse(
        content=json.loads(json.dumps(
            category.model_dump(by_alias=True),
            cls=JSONEncoder
        ))
    )


@app.post("/api/orders")
async def api_create_order(payload: Dict[str, Any]):
    """Create a new order (public endpoint)."""
    if OrderService is None or OrderCreateInput is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    try:
        order_data = OrderCreateInput(**payload)
        service = OrderService()
        order = await service.create(order_data)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if logger:
            logger.error(f"Order creation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create order: {str(e)}")

    return JSONResponse(
        content=json.loads(json.dumps(
            order.model_dump(by_alias=True),
            cls=JSONEncoder
        ))
    )


# ========== Admin Panel: Auth, Media Upload & Management ==========

class AdminLoginRequest(BaseModel):
    email: str
    password: str


async def require_admin(authorization: Optional[str] = Header(None)) -> str:
    """Validate the admin JWT from the 'Authorization: Bearer <token>' header."""
    if AdminAuthService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing admin token")
    token = authorization.split(" ", 1)[1].strip()
    email = AdminAuthService().verify_token(token)
    if not email:
        raise HTTPException(status_code=401, detail="Invalid or expired admin token")
    return email


@app.post("/api/admin/login")
async def admin_login(payload: AdminLoginRequest):
    """Authenticate the super admin and return a JWT."""
    if AdminAuthService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    token = await AdminAuthService().authenticate(payload.email, payload.password)
    if not token:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {"token": token, "email": payload.email}


@app.get("/api/admin/me")
async def admin_me(email: str = Depends(require_admin)):
    """Return the currently authenticated admin (used to verify a stored token)."""
    return {"email": email}


@app.post("/api/admin/upload")
async def admin_upload(
    files: List[UploadFile] = File(...),
    folder: str = Form("products"),
    email: str = Depends(require_admin),
):
    """Upload one or more media files to the Cloudflare R2 'chokmoki' bucket."""
    if R2Service is None:
        raise HTTPException(status_code=500, detail="R2 storage not initialized")

    safe_folder = "".join(c for c in folder if c.isalnum() or c in ("-", "_", "/")) or "products"
    service = R2Service()
    urls: List[str] = []
    try:
        for upload in files:
            content = await upload.read()
            try:
                extension, content_type = validate_upload(
                    content, upload.filename or "upload.bin"
                )
            except UploadValidationError as ve:
                raise HTTPException(status_code=400, detail=str(ve)) from ve
            url = await service.upload_file(
                content,
                extension=extension,
                content_type=content_type,
                folder=safe_folder,
            )
            urls.append(url)
    except HTTPException:
        raise
    except Exception as e:
        if logger:
            logger.error(f"Admin upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")

    return {"urls": urls}


@app.get("/api/admin/orders")
async def admin_list_orders(
    skip: int = 0,
    limit: int = 50,
    status: Optional[str] = None,
    search: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    email: str = Depends(require_admin),
):
    """List all orders for the admin dashboard with optional filtering."""
    if OrderService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    service = OrderService()
    orders = await service.list(
        skip=skip, limit=limit,
        status=status, search=search,
        from_date=from_date, to_date=to_date,
    )
    total = await service.count(
        status=status, search=search,
        from_date=from_date, to_date=to_date,
    )
    return JSONResponse(content=json.loads(json.dumps({
        "data": [order.model_dump(by_alias=True) for order in orders],
        "count": total,
    }, cls=JSONEncoder)))


@app.post("/api/admin/orders")
async def admin_create_order(
    payload: Dict[str, Any], email: str = Depends(require_admin)
):
    """Create an order from the admin dashboard (phone / manual orders)."""
    if OrderService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    try:
        service = OrderService()
        order = await service.create_from_admin(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if logger:
            logger.error(f"Admin order creation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create order: {str(e)}")

    return JSONResponse(
        content=json.loads(
            json.dumps(order.model_dump(by_alias=True), cls=JSONEncoder)
        )
    )


@app.put("/api/admin/orders/{order_id}/status")
async def admin_update_order_status(
    order_id: str, payload: Dict[str, Any], email: str = Depends(require_admin)
):
    """Update an order's status by order_id."""
    if OrderService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    try:
        status = OrderStatus(**payload.get("status", {}))
        service = OrderService()
        order = await service.get_by_id(order_id)
        if not order:
            order = await service.get_by_mongo_id(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        updated = await service.update_status(order.order_id, status)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not updated:
        raise HTTPException(status_code=404, detail="Order not found")
    return JSONResponse(content=json.loads(json.dumps(
        updated.model_dump(by_alias=True), cls=JSONEncoder
    )))


@app.get("/api/admin/orders/{order_id}")
async def admin_get_order(order_id: str, email: str = Depends(require_admin)):
    """Get a single order by order_id."""
    if OrderService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    service = OrderService()
    order = await service.get_by_id(order_id)
    if not order:
        order = await service.get_by_mongo_id(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return JSONResponse(content=json.loads(json.dumps(
        order.model_dump(by_alias=True), cls=JSONEncoder
    )))


@app.get("/api/admin/stats")
async def admin_get_stats(email: str = Depends(require_admin)):
    """Dashboard overview stats: order counts, revenue, product count."""
    if OrderService is None or ProductService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    database = await db.get_database()

    orders_collection = database["orders"]
    products_collection = database["products"]

    total_orders = await orders_collection.count_documents({})

    revenue_pipeline = [
        {"$match": {"status.type": {"$nin": ["rejected", "rejected_by_user"]}}},
        {"$group": {"_id": None, "total": {"$sum": "$total_amount"}}},
    ]
    revenue_result = await orders_collection.aggregate(revenue_pipeline).to_list(1)
    total_revenue = revenue_result[0]["total"] if revenue_result else 0

    status_pipeline = [
        {"$group": {"_id": "$status.type", "count": {"$sum": 1}}},
    ]
    status_result = await orders_collection.aggregate(status_pipeline).to_list(100)
    status_counts = {item["_id"]: item["count"] for item in status_result if item["_id"]}

    # Align "today" with store timezone (IST) — Mongo stores naive UTC datetimes.
    ist = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(ist)
    today_start_ist = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start = today_start_ist.astimezone(timezone.utc).replace(tzinfo=None)
    orders_today = await orders_collection.count_documents({"created_at": {"$gte": today_start}})

    total_products = await products_collection.count_documents({})
    active_products = await products_collection.count_documents({"active": True})

    return JSONResponse(content=json.loads(json.dumps({
        "totalOrders": total_orders,
        "totalRevenue": total_revenue,
        "ordersToday": orders_today,
        "statusCounts": status_counts,
        "totalProducts": total_products,
        "activeProducts": active_products,
    }, cls=JSONEncoder)))


@app.get("/api/admin/products")
async def admin_list_products(
    skip: int = 0,
    limit: int = 200,
    search: Optional[str] = None,
    category: Optional[str] = None,
    active: Optional[bool] = None,
    is_best_seller: Optional[bool] = None,
    is_curated: Optional[bool] = None,
    email: str = Depends(require_admin),
):
    """List every product (including inactive) for the admin dashboard."""
    if ProductService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    service = ProductService()
    products = await service.list(
        skip=skip, limit=limit, active=active,
        category=category, is_best_seller=is_best_seller, is_curated=is_curated, search=search,
    )
    total = await service.count(
        active=active, category=category, is_best_seller=is_best_seller, is_curated=is_curated, search=search
    )
    return JSONResponse(content=json.loads(json.dumps({
        "data": products,
        "count": total,
    }, cls=JSONEncoder)))


@app.post("/api/admin/products")
async def admin_create_product(
    payload: Dict[str, Any], email: str = Depends(require_admin)
):
    """Create a product. Media URLs should already point to R2 (see /api/admin/upload)."""
    if ProductService is None or JewelryProductCreate is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    try:
        product_data = JewelryProductCreate(**payload)
        product = await ProductService().create(product_data)
    except HTTPException:
        raise
    except ValueError as e:
        if "already exists" in str(e):
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    if cache:
        await cache.delete_pattern("chokmoki:products:*")
        await cache.delete_pattern("chokmoki:product:*")

    return JSONResponse(content=json.loads(json.dumps(
        product.model_dump(by_alias=True), cls=JSONEncoder
    )))


@app.get("/api/admin/products/{product_id}")
async def admin_get_product(product_id: str, email: str = Depends(require_admin)):
    """Get a single product by MongoDB id."""
    if ProductService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    product = await ProductService().get_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return JSONResponse(content=json.loads(json.dumps(
        product.model_dump(by_alias=True), cls=JSONEncoder
    )))


@app.put("/api/admin/products/{product_id}")
async def admin_update_product(
    product_id: str, payload: Dict[str, Any], email: str = Depends(require_admin)
):
    """Update a product by its MongoDB id."""
    if ProductService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    service = ProductService()
    existing = await service.get_by_id(product_id)
    try:
        updated = await service.update(product_id, payload)
    except ValueError as e:
        if "already exists" in str(e):
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="Product not found")

    if cache:
        if existing and existing.slug != updated.slug:
            await cache.delete(f"chokmoki:product:{existing.slug}")
        await cache.delete_pattern("chokmoki:products:*")
        await cache.delete_pattern("chokmoki:product:*")

    return JSONResponse(content=json.loads(json.dumps(
        updated.model_dump(by_alias=True), cls=JSONEncoder
    )))


@app.delete("/api/admin/products/{product_id}")
async def admin_delete_product(product_id: str, email: str = Depends(require_admin)):
    """Delete a product by its MongoDB id."""
    if ProductService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    service = ProductService()
    existing = await service.get_by_id(product_id)
    try:
        deleted = await service.delete(product_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail="Product not found")

    if cache:
        if existing:
            await cache.delete(f"chokmoki:product:{existing.slug}")
        await cache.delete_pattern("chokmoki:products:*")
        await cache.delete_pattern("chokmoki:product:*")

    return {"success": True}


@app.get("/api/admin/categories")
async def admin_list_categories(email: str = Depends(require_admin)):
    """List every category for the admin dashboard."""
    if CategoryService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    service = CategoryService()
    categories = await service.list(limit=100)
    return JSONResponse(content=json.loads(json.dumps({
        "data": [cat.model_dump(by_alias=True) for cat in categories],
        "count": len(categories),
    }, cls=JSONEncoder)))


@app.post("/api/admin/categories")
async def admin_create_category(
    payload: Dict[str, Any], email: str = Depends(require_admin)
):
    """Create a category."""
    if CategoryService is None or JewelryCategoryCreate is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    try:
        category_data = JewelryCategoryCreate(**payload)
        category = await CategoryService().create(category_data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if cache:
        await cache.delete("chokmoki:categories")

    return JSONResponse(content=json.loads(json.dumps(
        category.model_dump(by_alias=True), cls=JSONEncoder
    )))


_CATEGORY_UPDATE_FIELDS = frozenset({
    "slug", "name", "tagline", "banner", "thumbnail", "description", "sort_order", "active",
})


@app.put("/api/admin/categories/{category_id}")
async def admin_update_category(
    category_id: str, payload: Dict[str, Any], email: str = Depends(require_admin)
):
    """Update a category by its MongoDB id."""
    if CategoryService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    update_data = {k: v for k, v in payload.items() if k in _CATEGORY_UPDATE_FIELDS}
    if not update_data:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    try:
        updated = await CategoryService().update(category_id, update_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="Category not found")

    if cache:
        await cache.delete("chokmoki:categories")

    return JSONResponse(content=json.loads(json.dumps(
        updated.model_dump(by_alias=True), cls=JSONEncoder
    )))


@app.delete("/api/admin/categories/{category_id}")
async def admin_delete_category(category_id: str, email: str = Depends(require_admin)):
    """Delete a category by its MongoDB id."""
    if CategoryService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    try:
        deleted = await CategoryService().delete(category_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail="Category not found")

    if cache:
        await cache.delete("chokmoki:categories")

    return {"success": True}


# ========== Public Dynamic Content Endpoints ==========

@app.get("/api/testimonials")
async def api_list_testimonials():
    """List all active testimonials."""
    if TestimonialService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    service = TestimonialService()
    testimonials = await service.list(active=True)
    total = await service.count(active=True)
    
    return JSONResponse(content=_json_response_content({"data": testimonials, "count": total}))


@app.get("/api/hero")
async def api_get_hero_config():
    """Get the active hero configuration."""
    if HeroConfigService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    service = HeroConfigService()
    config = await service.get_active()
    if not config:
        return JSONResponse(content={"media_type": None, "media_url": None, "alt_text": None, "active": False})
    
    return JSONResponse(content=_json_response_content(config.model_dump(by_alias=True)))


# ========== Admin: Testimonials ==========

@app.get("/api/admin/testimonials")
async def admin_list_testimonials(
    skip: int = 0,
    limit: int = 20,
    email: str = Depends(require_admin),
):
    """List all testimonials for admin."""
    if TestimonialService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    service = TestimonialService()
    testimonials = await service.list(skip=skip, limit=limit)
    total = await service.count()
    
    return JSONResponse(content=json.loads(json.dumps({
        "data": testimonials,
        "count": total,
    }, cls=JSONEncoder)))


@app.post("/api/admin/testimonials")
async def admin_create_testimonial(
    payload: Dict[str, Any], email: str = Depends(require_admin)
):
    """Create a testimonial."""
    if TestimonialService is None or TestimonialCreate is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    try:
        data = TestimonialCreate(**payload)
        testimonial = await TestimonialService().create(data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return JSONResponse(content=json.loads(json.dumps(
        testimonial.model_dump(by_alias=True), cls=JSONEncoder
    )))


@app.put("/api/admin/testimonials/{testimonial_id}")
async def admin_update_testimonial(
    testimonial_id: str, payload: Dict[str, Any], email: str = Depends(require_admin)
):
    """Update a testimonial by its MongoDB id."""
    if TestimonialService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    try:
        updated = await TestimonialService().update(testimonial_id, payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="Testimonial not found")
    return JSONResponse(content=json.loads(json.dumps(
        updated.model_dump(by_alias=True), cls=JSONEncoder
    )))


@app.delete("/api/admin/testimonials/{testimonial_id}")
async def admin_delete_testimonial(testimonial_id: str, email: str = Depends(require_admin)):
    """Delete a testimonial by its MongoDB id."""
    if TestimonialService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    try:
        deleted = await TestimonialService().delete(testimonial_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail="Testimonial not found")
    return {"success": True}


# ========== Admin: Hero Config ==========

@app.get("/api/admin/hero")
async def admin_list_hero_configs(email: str = Depends(require_admin)):
    """List all hero configs for admin."""
    if HeroConfigService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    service = HeroConfigService()
    configs = await service.list()
    total = await service.count()
    
    return JSONResponse(content=json.loads(json.dumps({
        "data": configs,
        "count": total,
    }, cls=JSONEncoder)))


@app.post("/api/admin/hero")
async def admin_create_hero_config(
    payload: Dict[str, Any], email: str = Depends(require_admin)
):
    """Create a hero config."""
    if HeroConfigService is None or HeroConfigCreate is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    try:
        data = HeroConfigCreate(**payload)
        config = await HeroConfigService().create(data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return JSONResponse(content=json.loads(json.dumps(
        config.model_dump(by_alias=True), cls=JSONEncoder
    )))


@app.put("/api/admin/hero/{config_id}")
async def admin_update_hero_config(
    config_id: str, payload: Dict[str, Any], email: str = Depends(require_admin)
):
    """Update a hero config by its MongoDB id."""
    if HeroConfigService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    service = HeroConfigService()
    existing = await service.get_by_id(config_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Hero config not found")

    try:
        merged = {**existing.model_dump(), **payload}
        data = HeroConfigCreate(**merged)
        updated = await service.update(config_id, data.model_dump())
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not updated:
        updated = await service.get_by_id(config_id)
    return JSONResponse(content=json.loads(json.dumps(
        updated.model_dump(by_alias=True), cls=JSONEncoder
    )))


@app.delete("/api/admin/hero/{config_id}")
async def admin_delete_hero_config(config_id: str, email: str = Depends(require_admin)):
    """Delete a hero config by its MongoDB id."""
    if HeroConfigService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    try:
        deleted = await HeroConfigService().delete(config_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail="Hero config not found")
    return {"success": True}


# ========== Public: Site Assets ==========

@app.get("/api/site-assets")
async def api_list_site_assets():
    """List all active site assets."""
    if SiteAssetService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    service = SiteAssetService()
    assets = await service.list(active=True)
    return JSONResponse(content=_json_response_content({"data": assets, "count": len(assets)}))


@app.get("/api/site-assets/{key}")
async def api_get_site_asset(key: str):
    """Get a single active site asset by key."""
    if SiteAssetService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    service = SiteAssetService()
    asset = await service.get_by_key(key)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    return JSONResponse(
        content=json.loads(json.dumps(
            asset.model_dump(by_alias=True),
            cls=JSONEncoder
        ))
    )


# ========== Public: FAQ ==========

@app.get("/api/faq")
async def api_list_faq(scope: Optional[str] = None):
    """List active FAQ items, optionally filtered by scope."""
    if FAQItemService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    service = FAQItemService()
    items = await service.list(scope=scope, active=True)
    return JSONResponse(content=_json_response_content({"data": items, "count": len(items)}))


# ========== Public: Collection Slides ==========

@app.get("/api/collection-slides")
async def api_list_collection_slides():
    """List all active collection slides."""
    if CollectionSlideService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    service = CollectionSlideService()
    slides = await service.list(active=True)
    return JSONResponse(content=_json_response_content({"data": slides, "count": len(slides)}))


# ========== Admin: Site Assets ==========

@app.get("/api/admin/site-assets")
async def admin_list_site_assets(email: str = Depends(require_admin)):
    """List all site assets for admin."""
    if SiteAssetService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    service = SiteAssetService()
    assets = await service.list()
    return JSONResponse(content=json.loads(json.dumps({
        "data": assets,
        "count": len(assets),
    }, cls=JSONEncoder)))


@app.post("/api/admin/site-assets")
async def admin_create_site_asset(
    payload: Dict[str, Any], email: str = Depends(require_admin)
):
    """Create a site asset."""
    if SiteAssetService is None or SiteAssetCreate is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    try:
        data = SiteAssetCreate(**payload)
        asset = await SiteAssetService().create(data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return JSONResponse(content=json.loads(json.dumps(
        asset.model_dump(by_alias=True), cls=JSONEncoder
    )))


@app.put("/api/admin/site-assets/{asset_id}")
async def admin_update_site_asset(
    asset_id: str, payload: Dict[str, Any], email: str = Depends(require_admin)
):
    """Update a site asset by its MongoDB id."""
    if SiteAssetService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    try:
        updated = await SiteAssetService().update(asset_id, payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="Site asset not found")
    return JSONResponse(content=json.loads(json.dumps(
        updated.model_dump(by_alias=True), cls=JSONEncoder
    )))


@app.delete("/api/admin/site-assets/{asset_id}")
async def admin_delete_site_asset(asset_id: str, email: str = Depends(require_admin)):
    """Delete a site asset by its MongoDB id."""
    if SiteAssetService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    try:
        deleted = await SiteAssetService().delete(asset_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail="Site asset not found")
    return {"success": True}


# ========== Admin: FAQ ==========

@app.get("/api/admin/faq")
async def admin_list_faq_items(email: str = Depends(require_admin)):
    """List all FAQ items for admin."""
    if FAQItemService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    service = FAQItemService()
    items = await service.list()
    return JSONResponse(content=json.loads(json.dumps({
        "data": items,
        "count": len(items),
    }, cls=JSONEncoder)))


@app.post("/api/admin/faq")
async def admin_create_faq_item(
    payload: Dict[str, Any], email: str = Depends(require_admin)
):
    """Create a FAQ item."""
    if FAQItemService is None or FAQItemCreate is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    try:
        data = FAQItemCreate(**payload)
        item = await FAQItemService().create(data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return JSONResponse(content=json.loads(json.dumps(
        item.model_dump(by_alias=True), cls=JSONEncoder
    )))


@app.put("/api/admin/faq/{faq_id}")
async def admin_update_faq_item(
    faq_id: str, payload: Dict[str, Any], email: str = Depends(require_admin)
):
    """Update a FAQ item by its MongoDB id."""
    if FAQItemService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    try:
        updated = await FAQItemService().update(faq_id, payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="FAQ item not found")
    return JSONResponse(content=json.loads(json.dumps(
        updated.model_dump(by_alias=True), cls=JSONEncoder
    )))


@app.delete("/api/admin/faq/{faq_id}")
async def admin_delete_faq_item(faq_id: str, email: str = Depends(require_admin)):
    """Delete a FAQ item by its MongoDB id."""
    if FAQItemService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    try:
        deleted = await FAQItemService().delete(faq_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail="FAQ item not found")
    return {"success": True}


# ========== Admin: Collection Slides ==========

@app.get("/api/admin/collection-slides")
async def admin_list_collection_slides(email: str = Depends(require_admin)):
    """List all collection slides for admin."""
    if CollectionSlideService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    service = CollectionSlideService()
    slides = await service.list()
    return JSONResponse(content=json.loads(json.dumps({
        "data": slides,
        "count": len(slides),
    }, cls=JSONEncoder)))


@app.post("/api/admin/collection-slides")
async def admin_create_collection_slide(
    payload: Dict[str, Any], email: str = Depends(require_admin)
):
    """Create a collection slide."""
    if CollectionSlideService is None or CollectionSlideCreate is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    try:
        data = CollectionSlideCreate(**payload)
        slide = await CollectionSlideService().create(data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return JSONResponse(content=json.loads(json.dumps(
        slide.model_dump(by_alias=True), cls=JSONEncoder
    )))


@app.put("/api/admin/collection-slides/{slide_id}")
async def admin_update_collection_slide(
    slide_id: str, payload: Dict[str, Any], email: str = Depends(require_admin)
):
    """Update a collection slide by its MongoDB id."""
    if CollectionSlideService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    try:
        updated = await CollectionSlideService().update(slide_id, payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="Collection slide not found")
    return JSONResponse(content=json.loads(json.dumps(
        updated.model_dump(by_alias=True), cls=JSONEncoder
    )))


@app.delete("/api/admin/collection-slides/{slide_id}")
async def admin_delete_collection_slide(slide_id: str, email: str = Depends(require_admin)):
    """Delete a collection slide by its MongoDB id."""
    if CollectionSlideService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    try:
        deleted = await CollectionSlideService().delete(slide_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail="Collection slide not found")
    return {"success": True}


# ========== Public: Studio, Shop page, Policies ==========

@app.get("/api/studio-settings")
async def api_get_studio_settings():
    if StudioSettingsService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    data = await StudioSettingsService().get_public()
    return JSONResponse(content=_json_response_content({"data": data}))


@app.get("/api/shop-page")
async def api_get_shop_page():
    if ShopPageSettingsService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    data = await ShopPageSettingsService().get_public()
    return JSONResponse(content=_json_response_content({"data": data}))


@app.get("/api/policies")
async def api_get_policies():
    if PolicyContentService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    bundle = await PolicyContentService().get_public_bundle()
    return JSONResponse(content=_json_response_content(bundle))


# ========== Admin: Studio settings ==========

@app.get("/api/admin/studio-settings")
async def admin_get_studio_settings(email: str = Depends(require_admin)):
    if StudioSettingsService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    settings = await StudioSettingsService().get_admin()
    return JSONResponse(content=_json_response_content({
        "data": settings.model_dump(by_alias=True) if settings else None,
    }))


@app.put("/api/admin/studio-settings")
async def admin_upsert_studio_settings(
    payload: Dict[str, Any], email: str = Depends(require_admin)
):
    if StudioSettingsService is None or StudioSettingsUpdate is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    try:
        data = StudioSettingsUpdate(**payload)
        updated = await StudioSettingsService().upsert(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return JSONResponse(content=json.loads(json.dumps(
        updated.model_dump(by_alias=True), cls=JSONEncoder
    )))


# ========== Admin: Shop page ==========

@app.get("/api/admin/shop-page")
async def admin_get_shop_page(email: str = Depends(require_admin)):
    if ShopPageSettingsService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    settings = await ShopPageSettingsService().get_admin()
    return JSONResponse(content=_json_response_content({
        "data": settings.model_dump(by_alias=True) if settings else None,
    }))


@app.put("/api/admin/shop-page")
async def admin_upsert_shop_page(
    payload: Dict[str, Any], email: str = Depends(require_admin)
):
    if ShopPageSettingsService is None or ShopPageSettingsUpdate is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    try:
        data = ShopPageSettingsUpdate(**payload)
        updated = await ShopPageSettingsService().upsert(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return JSONResponse(content=json.loads(json.dumps(
        updated.model_dump(by_alias=True), cls=JSONEncoder
    )))


# ========== Admin: Policies ==========

@app.get("/api/admin/policies")
async def admin_get_policies(email: str = Depends(require_admin)):
    if PolicyContentService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    bundle = await PolicyContentService().get_admin_bundle()
    return JSONResponse(content=_json_response_content(bundle))


@app.put("/api/admin/policies/meta")
async def admin_upsert_policy_meta(
    payload: Dict[str, Any], email: str = Depends(require_admin)
):
    if PolicyContentService is None or PolicyPageMetaUpdate is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    try:
        data = PolicyPageMetaUpdate(**payload)
        updated = await PolicyContentService().upsert_meta(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return JSONResponse(content=json.loads(json.dumps(
        updated.model_dump(by_alias=True), cls=JSONEncoder
    )))


@app.get("/api/admin/policies/meta")
async def admin_get_policy_meta(email: str = Depends(require_admin)):
    if PolicyContentService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    bundle = await PolicyContentService().get_admin_bundle()
    return JSONResponse(content=_json_response_content(bundle.get("meta")))


@app.put("/api/admin/policies/sections/{slug}")
async def admin_upsert_policy_section(
    slug: str, payload: Dict[str, Any], email: str = Depends(require_admin)
):
    if PolicyContentService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    try:
        updated = await PolicyContentService().upsert_section_by_slug(slug, payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return JSONResponse(content=json.loads(json.dumps(
        updated.model_dump(by_alias=True), cls=JSONEncoder
    )))


@app.post("/api/admin/policies/sections")
async def admin_create_policy_section(
    payload: Dict[str, Any], email: str = Depends(require_admin)
):
    if PolicyContentService is None or PolicySectionCreate is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    try:
        data = PolicySectionCreate(**payload)
        if not data.slug or not data.slug.strip():
            raise HTTPException(status_code=400, detail="slug is required")
        service = PolicyContentService()
        if await service.slug_exists(data.slug.strip()):
            raise HTTPException(status_code=409, detail="A section with this slug already exists")
        created = await service.create_section(data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return JSONResponse(
        status_code=201,
        content=json.loads(json.dumps(created.model_dump(by_alias=True), cls=JSONEncoder)),
    )


@app.delete("/api/admin/policies/sections/{slug}")
async def admin_delete_policy_section(
    slug: str, email: str = Depends(require_admin)
):
    if PolicyContentService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    deleted = await PolicyContentService().delete_section_by_slug(slug)
    if not deleted:
        raise HTTPException(status_code=404, detail="Policy section not found")
    return JSONResponse(content={"success": True, "slug": slug})


# ========== Public: Home, Story, Journal, Inbox ==========

@app.get("/api/home-page")
async def api_get_home_page():
    if HomePageSettingsService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    data = await HomePageSettingsService().get_public()
    return JSONResponse(content=_json_response_content({"data": data}))


@app.get("/api/story-page")
async def api_get_story_page():
    if StoryPageSettingsService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    data = await StoryPageSettingsService().get_public()
    return JSONResponse(content=_json_response_content({"data": data}))


@app.get("/api/navigation")
async def api_get_navigation():
    if NavigationSettingsService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    data = await NavigationSettingsService().get_public()
    return JSONResponse(content=_json_response_content({"data": data}))


@app.get("/api/contact-page")
async def api_get_contact_page():
    if ContactPageSettingsService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    data = await ContactPageSettingsService().get_public()
    return JSONResponse(content=_json_response_content({"data": data}))


@app.get("/api/history-page")
async def api_get_history_page():
    if HistoryPageSettingsService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    data = await HistoryPageSettingsService().get_public()
    return JSONResponse(content=_json_response_content({"data": data}))


@app.get("/api/product-page")
async def api_get_product_page():
    if ProductPageSettingsService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    data = await ProductPageSettingsService().get_public()
    return JSONResponse(content=_json_response_content({"data": data}))


@app.get("/api/journal")
async def api_get_journal():
    if BlogService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    service = BlogService()
    meta = await service.get_journal_public()
    posts = await service.list_posts(active=True, limit=50)
    return JSONResponse(content=_json_response_content({
        "meta": meta,
        "data": posts,
        "count": len(posts),
    }))


@app.post("/api/contact")
async def api_submit_contact(payload: Dict[str, Any]):
    if InboxService is None or ContactSubmissionCreate is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    try:
        data = ContactSubmissionCreate(**payload)
        created = await InboxService().create_contact(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return JSONResponse(content=_json_response_content({
        "success": True,
        "id": str(created.id),
    }))


@app.post("/api/newsletter")
async def api_subscribe_newsletter(payload: Dict[str, Any]):
    if InboxService is None or NewsletterSubscribeCreate is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    try:
        data = NewsletterSubscribeCreate(**payload)
        created = await InboxService().subscribe_newsletter(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return JSONResponse(content=_json_response_content({
        "success": True,
        "id": str(created.id),
    }))


# ========== Admin: Home & Story pages ==========

@app.get("/api/admin/home-page")
async def admin_get_home_page(email: str = Depends(require_admin)):
    if HomePageSettingsService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    settings = await HomePageSettingsService().get_admin()
    return JSONResponse(content=_json_response_content({
        "data": settings.model_dump(by_alias=True) if settings else None,
    }))


@app.put("/api/admin/home-page")
async def admin_upsert_home_page(
    payload: Dict[str, Any], email: str = Depends(require_admin)
):
    if HomePageSettingsService is None or HomePageSettingsUpdate is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    try:
        data = HomePageSettingsUpdate(**payload)
        updated = await HomePageSettingsService().upsert(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return JSONResponse(content=json.loads(json.dumps(
        updated.model_dump(by_alias=True), cls=JSONEncoder
    )))


@app.get("/api/admin/story-page")
async def admin_get_story_page(email: str = Depends(require_admin)):
    if StoryPageSettingsService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    settings = await StoryPageSettingsService().get_admin()
    return JSONResponse(content=_json_response_content({
        "data": settings.model_dump(by_alias=True) if settings else None,
    }))


@app.put("/api/admin/story-page")
async def admin_upsert_story_page(
    payload: Dict[str, Any], email: str = Depends(require_admin)
):
    if StoryPageSettingsService is None or StoryPageSettingsUpdate is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    try:
        data = StoryPageSettingsUpdate(**payload)
        updated = await StoryPageSettingsService().upsert(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return JSONResponse(content=json.loads(json.dumps(
        updated.model_dump(by_alias=True), cls=JSONEncoder
    )))


@app.get("/api/admin/navigation")
async def admin_get_navigation(email: str = Depends(require_admin)):
    if NavigationSettingsService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    settings = await NavigationSettingsService().get_admin()
    return JSONResponse(content=_json_response_content({
        "data": settings.model_dump(by_alias=True) if settings else None,
    }))


@app.put("/api/admin/navigation")
async def admin_upsert_navigation(
    payload: Dict[str, Any], email: str = Depends(require_admin)
):
    if NavigationSettingsService is None or NavigationSettingsUpdate is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    try:
        data = NavigationSettingsUpdate(**payload)
        updated = await NavigationSettingsService().upsert(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return JSONResponse(content=json.loads(json.dumps(
        updated.model_dump(by_alias=True), cls=JSONEncoder
    )))


@app.get("/api/admin/contact-page")
async def admin_get_contact_page(email: str = Depends(require_admin)):
    if ContactPageSettingsService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    settings = await ContactPageSettingsService().get_admin()
    return JSONResponse(content=_json_response_content({
        "data": settings.model_dump(by_alias=True) if settings else None,
    }))


@app.put("/api/admin/contact-page")
async def admin_upsert_contact_page(
    payload: Dict[str, Any], email: str = Depends(require_admin)
):
    if ContactPageSettingsService is None or ContactPageSettingsUpdate is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    try:
        data = ContactPageSettingsUpdate(**payload)
        updated = await ContactPageSettingsService().upsert(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return JSONResponse(content=json.loads(json.dumps(
        updated.model_dump(by_alias=True), cls=JSONEncoder
    )))


@app.get("/api/admin/history-page")
async def admin_get_history_page(email: str = Depends(require_admin)):
    if HistoryPageSettingsService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    settings = await HistoryPageSettingsService().get_admin()
    return JSONResponse(content=_json_response_content({
        "data": settings.model_dump(by_alias=True) if settings else None,
    }))


@app.put("/api/admin/history-page")
async def admin_upsert_history_page(
    payload: Dict[str, Any], email: str = Depends(require_admin)
):
    if HistoryPageSettingsService is None or HistoryPageSettingsUpdate is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    try:
        data = HistoryPageSettingsUpdate(**payload)
        updated = await HistoryPageSettingsService().upsert(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return JSONResponse(content=json.loads(json.dumps(
        updated.model_dump(by_alias=True), cls=JSONEncoder
    )))


@app.get("/api/admin/product-page")
async def admin_get_product_page(email: str = Depends(require_admin)):
    if ProductPageSettingsService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    settings = await ProductPageSettingsService().get_admin()
    return JSONResponse(content=_json_response_content({
        "data": settings.model_dump(by_alias=True) if settings else None,
    }))


@app.put("/api/admin/product-page")
async def admin_upsert_product_page(
    payload: Dict[str, Any], email: str = Depends(require_admin)
):
    if ProductPageSettingsService is None or ProductPageSettingsUpdate is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    try:
        data = ProductPageSettingsUpdate(**payload)
        updated = await ProductPageSettingsService().upsert(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return JSONResponse(content=json.loads(json.dumps(
        updated.model_dump(by_alias=True), cls=JSONEncoder
    )))


# ========== Admin: Journal / Blog ==========

@app.get("/api/admin/journal")
async def admin_get_journal(email: str = Depends(require_admin)):
    if BlogService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    service = BlogService()
    meta = await service.get_journal_admin()
    posts = await service.list_posts(limit=200)
    return JSONResponse(content=_json_response_content({
        "meta": meta.model_dump(by_alias=True) if meta else None,
        "data": posts,
        "count": len(posts),
    }))


@app.put("/api/admin/journal/meta")
async def admin_upsert_journal_meta(
    payload: Dict[str, Any], email: str = Depends(require_admin)
):
    if BlogService is None or JournalPageSettingsUpdate is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    try:
        data = JournalPageSettingsUpdate(**payload)
        updated = await BlogService().upsert_journal(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return JSONResponse(content=json.loads(json.dumps(
        updated.model_dump(by_alias=True), cls=JSONEncoder
    )))


@app.get("/api/admin/journal/meta")
async def admin_get_journal_meta(email: str = Depends(require_admin)):
    if BlogService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    meta = await BlogService().get_journal_admin()
    return JSONResponse(content=_json_response_content(
        meta.model_dump(by_alias=True) if meta else None
    ))


@app.post("/api/admin/blog-posts")
async def admin_create_blog_post(
    payload: Dict[str, Any], email: str = Depends(require_admin)
):
    if BlogService is None or BlogPostCreate is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    if "published" in payload and "active" not in payload:
        payload = {**payload, "active": payload["published"]}
    if "content" in payload and "body" not in payload:
        payload = {**payload, "body": payload["content"]}
    try:
        data = BlogPostCreate(**payload)
        created = await BlogService().create_post(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return JSONResponse(content=json.loads(json.dumps(
        created.model_dump(by_alias=True), cls=JSONEncoder
    )))


@app.put("/api/admin/blog-posts/{post_id}")
async def admin_update_blog_post(
    post_id: str, payload: Dict[str, Any], email: str = Depends(require_admin)
):
    if BlogService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    try:
        updated = await BlogService().update_post(post_id, payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="Blog post not found")
    return JSONResponse(content=json.loads(json.dumps(
        updated.model_dump(by_alias=True), cls=JSONEncoder
    )))


@app.delete("/api/admin/blog-posts/{post_id}")
async def admin_delete_blog_post(post_id: str, email: str = Depends(require_admin)):
    if BlogService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    deleted = await BlogService().delete_post(post_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Blog post not found")
    return {"success": True}


# ========== Admin: Inbox (contact + newsletter) ==========

@app.get("/api/admin/inbox")
async def admin_get_inbox(
    skip: int = 0,
    limit: int = 100,
    email: str = Depends(require_admin),
):
    if InboxService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    service = InboxService()
    contacts = await service.list_contacts(skip=skip, limit=limit)
    newsletter = await service.list_newsletter(skip=skip, limit=limit)
    return JSONResponse(content=_json_response_content({
        "contacts": contacts,
        "contacts_count": await service.count_contacts(),
        "contacts_unread": await service.count_contacts(unread_only=True),
        "newsletter": newsletter,
        "newsletter_count": await service.count_newsletter(),
        "newsletter_unread": await service.count_newsletter(unread_only=True),
    }))


@app.patch("/api/admin/inbox/contacts/{submission_id}")
async def admin_patch_contact(
    submission_id: str, payload: Dict[str, Any], email: str = Depends(require_admin)
):
    if InboxService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    read = payload.get("read", True)
    ok = await InboxService().mark_contact_read(submission_id, bool(read))
    if not ok:
        raise HTTPException(status_code=404, detail="Contact submission not found")
    return {"success": True}


@app.delete("/api/admin/inbox/contacts/{submission_id}")
async def admin_delete_contact(submission_id: str, email: str = Depends(require_admin)):
    if InboxService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    if not await InboxService().delete_contact(submission_id):
        raise HTTPException(status_code=404, detail="Contact submission not found")
    return {"success": True}


@app.patch("/api/admin/inbox/newsletter/{sub_id}")
async def admin_patch_newsletter(
    sub_id: str, payload: Dict[str, Any], email: str = Depends(require_admin)
):
    if InboxService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    read = payload.get("read", True)
    ok = await InboxService().mark_newsletter_read(sub_id, bool(read))
    if not ok:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return {"success": True}


@app.delete("/api/admin/inbox/newsletter/{sub_id}")
async def admin_delete_newsletter(sub_id: str, email: str = Depends(require_admin)):
    if InboxService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    if not await InboxService().delete_newsletter(sub_id):
        raise HTTPException(status_code=404, detail="Subscription not found")
    return {"success": True}


# ========== Existing CQRS Endpoint ==========

@app.post("/")
async def handle_request(request: APIRequest):
    if CQRSRouter is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    if request.type not in {"query", "mutation"}:
        raise HTTPException(status_code=400, detail="Invalid type")

    try:
        if request.type == "query":
            result = await CQRSRouter.execute_query(
                request.operation, request.params, request.adminKey
            )
        else:
            result = await CQRSRouter.execute_mutation(
                request.operation, request.params, request.adminKey
            )

        return JSONResponse(
            content=json.loads(json.dumps(result, cls=JSONEncoder))
        )

    except HTTPException:
        raise
    except Exception as e:
        if logger:
            logger.error(str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/webhook/razorpay")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: Optional[str] = Header(None, alias="X-Razorpay-Signature")
):
    """Razorpay webhook endpoint with HMAC verification"""
    if RazorpayService is None or OrderService is None:
        raise HTTPException(status_code=500, detail="Services not initialized")
    
    try:
        body = await request.body()
        payload = body.decode('utf-8')
        
        if not x_razorpay_signature:
            logger.warning("Webhook request missing X-Razorpay-Signature header")
            raise HTTPException(status_code=400, detail="Missing X-Razorpay-Signature header")
        
        if not settings or not settings.razorpay_webhook_secret:
            logger.error(
                "RAZORPAY_WEBHOOK_SECRET is not set in environment variables. "
                "If you configured a webhook secret in Razorpay Dashboard, you must set RAZORPAY_WEBHOOK_SECRET in your .env file."
            )
            raise HTTPException(
                status_code=500, 
                detail="Webhook secret not configured. Please set RAZORPAY_WEBHOOK_SECRET in your environment variables."
            )
        
        razorpay_service = RazorpayService()
        if not razorpay_service.verify_webhook_signature(payload, x_razorpay_signature):
            logger.error(
                f"Webhook signature verification failed. "
                f"Make sure RAZORPAY_WEBHOOK_SECRET matches the secret set in Razorpay Dashboard. "
                f"Signature received: {x_razorpay_signature[:30]}..."
            )
            raise HTTPException(status_code=400, detail="Invalid webhook signature")
        
        webhook_data = json.loads(payload)
        event = webhook_data.get("event")
        payload_data = webhook_data.get("payload", {})
        
        if event == "payment.captured":
            payment_entity = payload_data.get("payment", {}).get("entity", {})
            
            razorpay_payment_id = payment_entity.get("id")
            razorpay_order_id = payment_entity.get("order_id")
            order_id = payment_entity.get("notes", {}).get("order_id")
            
            if not all([order_id, razorpay_order_id, razorpay_payment_id]):
                logger.warning(f"Incomplete webhook data. Missing: order_id={order_id}, razorpay_order_id={razorpay_order_id}, razorpay_payment_id={razorpay_payment_id}")
                logger.debug(f"Full webhook payload: {webhook_data}")
                return JSONResponse(content={"status": "ignored", "reason": "incomplete_data"})
            
            order_service = OrderService()
            try:
                _order, completion_status = await order_service.complete_pending_order(
                    order_id, razorpay_order_id, razorpay_payment_id
                )
                if completion_status == "not_found":
                    logger.warning(
                        f"Order {order_id} not found in Redis, may already be processed"
                    )
                    return JSONResponse(
                        content={"status": "ignored", "reason": "order_not_found"}
                    )
                message = (
                    "already_processed"
                    if completion_status == "existing"
                    else "created"
                )
                return JSONResponse(
                    content={
                        "status": "success",
                        "order_id": order_id,
                        "message": message,
                    }
                )
            except Exception as e:
                logger.error(f"Failed to process webhook for order {order_id}: {e}")
                raise HTTPException(
                    status_code=500, detail=f"Failed to process order: {str(e)}"
                )
        
        logger.info(f"Webhook event {event} received but not processed")
        return JSONResponse(content={"status": "ignored", "event": event})
    
    except HTTPException:
        raise
    except Exception as e:
        if logger:
            logger.error(f"Webhook processing error: {e}")
        raise HTTPException(status_code=500, detail="Webhook processing failed")


@app.get("/health")
async def health_check():
    """Comprehensive health check with system stats, database stats, and environment info"""
    
    async def get_db_stats():
        """Get MongoDB database statistics"""
        try:
            if db is None:
                return {"status": "not_available", "error": "Database not initialized"}
            
            database = await db.get_database()
            
            # Get all collection names
            collections = await database.list_collection_names()
            
            # Get counts for main collections in parallel
            collection_tasks = []
            for collection_name in collections:
                collection = database[collection_name]
                collection_tasks.append(collection.count_documents({}))
            
            counts = await asyncio.gather(*collection_tasks, return_exceptions=True)
            
            collection_stats = {}
            for i, collection_name in enumerate(collections):
                count = counts[i]
                if isinstance(count, Exception):
                    collection_stats[collection_name] = {"count": 0, "error": str(count)}
                else:
                    collection_stats[collection_name] = {"count": count}
            
            # Get database stats
            db_stats = await database.command("dbStats")
            
            return {
                "status": "connected",
                "database_name": settings.mongodb_db_name if settings else "unknown",
                "collections": collection_stats,
                "database_size": {
                    "dataSize": db_stats.get("dataSize", 0),
                    "storageSize": db_stats.get("storageSize", 0),
                    "indexSize": db_stats.get("indexSize", 0),
                    "collections": db_stats.get("collections", 0),
                }
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    async def get_redis_stats():
        """Get Redis connection statistics"""
        try:
            if redis_client is None:
                return {"status": "not_available", "error": "Redis not initialized"}
            
            client = await redis_client.get_client()
            info = await client.info()
            
            return {
                "status": "connected",
                "redis_version": info.get("redis_version", "unknown"),
                "used_memory": info.get("used_memory_human", "unknown"),
                "connected_clients": info.get("connected_clients", 0),
                "total_commands_processed": info.get("total_commands_processed", 0),
                "keyspace": {
                    "keys": info.get("db0", {}).get("keys", 0) if "db0" in str(info) else 0
                }
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    async def get_environment_info():
        """Get environment and system information"""
        try:
            env_info = {}
            if settings:
                env_info = {
                    "mongodb_db_name": settings.mongodb_db_name,
                    "log_level": settings.log_level,
                    "has_admin_login": bool(settings.admin_email and settings.admin_password),
                    "has_redis_url": bool(settings.redis_url),
                }
            
            return {
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                "system": platform.system(),
                "processor": platform.processor(),
                "environment": os.getenv("ENVIRONMENT", "development"),
                "settings": env_info
            }
        except Exception as e:
            return {"error": str(e)}
    
    async def get_service_status():
        """Get status of various services"""
        return {
            "database": "available" if db is not None else "not_available",
            "redis": "available" if redis_client is not None else "not_available",
            "cqrs_router": "available" if CQRSRouter is not None else "not_available",
            "logger": "available" if logger is not None else "not_available",
        }
    
    # Fetch all stats in parallel
    db_stats_task = get_db_stats()
    redis_stats_task = get_redis_stats()
    env_info_task = get_environment_info()
    service_status_task = get_service_status()
    
    db_stats, redis_stats, env_info, service_status = await asyncio.gather(
        db_stats_task,
        redis_stats_task,
        env_info_task,
        service_status_task,
        return_exceptions=True
    )
    
    # Handle exceptions
    if isinstance(db_stats, Exception):
        db_stats = {"status": "error", "error": str(db_stats)}
    if isinstance(redis_stats, Exception):
        redis_stats = {"status": "error", "error": str(redis_stats)}
    if isinstance(env_info, Exception):
        env_info = {"error": str(env_info)}
    if isinstance(service_status, Exception):
        service_status = {"error": str(service_status)}
    
    # Determine overall health status
    overall_status = "healthy"
    if db_stats.get("status") != "connected":
        overall_status = "degraded"
    if redis_stats.get("status") != "connected":
        overall_status = "degraded"
    
    return {
        "status": overall_status,
        "timestamp": datetime.utcnow().isoformat(),
        "services": service_status,
        "database": db_stats,
        "redis": redis_stats,
        "environment": env_info,
    }


@app.post("/cron/telegram/notify")
async def telegram_notify_cron():
    """Cron endpoint to process and send Telegram notifications"""
    if TelegramService is None:
        raise HTTPException(status_code=500, detail="TelegramService not initialized")
    
    try:
        telegram_service = TelegramService()
        result = await telegram_service.process_and_send_notifications()
        
        if result.success:
            return JSONResponse(content=result.model_dump())
        else:
            raise HTTPException(status_code=500, detail=result.message)
    except HTTPException:
        raise
    except Exception as e:
        if logger:
            logger.error(f"Telegram cron error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
