"""Public, read-only storefront content endpoints (no auth)."""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
import json
from api.bootstrap import AccountPageSettingsService, BlogService, CategoryService, CollectionSlideService, ContactPageSettingsService, FAQItemService, HeroConfigService, HistoryPageSettingsService, HomePageSettingsService, NavigationSettingsService, PolicyContentService, ProductPageSettingsService, ProductService, ShopPageSettingsService, SiteAssetService, StoryPageSettingsService, StudioSettingsService, TestimonialService, cache, settings
from api.json_utils import JSONEncoder, _json_dumps, _json_response_content
from src.services.product_filters import parse_ids_query

router = APIRouter()


async def _cache_products_key(category, search, sort, skip, limit, is_best_seller=None, is_curated=None, ids=None):
    return (
        f"chokmoki:products:{category or 'all'}:{search or 'all'}:{sort or 'default'}"
        f":bs{is_best_seller}:cur{is_curated}:{skip}:{limit}:ids{ids or 'all'}"
    )


@router.get("/api/products")
async def api_list_products(
    category: Optional[str] = None,
    search: Optional[str] = None,
    sort: Optional[str] = None,
    is_best_seller: Optional[bool] = None,
    is_curated: Optional[bool] = None,
    ids: Optional[str] = Query(default=None),
    skip: int = 0,
    limit: int = 50,
):
    """List products with optional filtering (cached)"""
    if ProductService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    id_list = parse_ids_query(ids)
    if id_list:
        limit = max(limit, len(id_list))
    
    cache_key = await _cache_products_key(
        category, search, sort, skip, limit, is_best_seller, is_curated, ",".join(id_list) if id_list else None
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
        ids=id_list,
    )
    total = await service.count(
        active=True, category=category, search=search,
        is_best_seller=is_best_seller, is_curated=is_curated,
        ids=id_list,
    )
    result = {"data": products, "count": total}
    
    if cache:
        await cache.set(cache_key, _json_dumps(result), 300)
    
    return JSONResponse(content=_json_response_content(result))


@router.get("/api/products/{slug}")
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


@router.get("/api/categories")
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


@router.get("/api/categories/{slug}")
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

@router.get("/api/testimonials")
async def api_list_testimonials():
    """List all active testimonials."""
    if TestimonialService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    service = TestimonialService()
    testimonials = await service.list(active=True)
    total = await service.count(active=True)
    
    return JSONResponse(content=_json_response_content({"data": testimonials, "count": total}))


@router.get("/api/hero")
async def api_get_hero_config():
    """Get the active hero configuration."""
    if HeroConfigService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    service = HeroConfigService()
    config = await service.get_active()
    if not config:
        return JSONResponse(content={"media_type": None, "media_url": None, "alt_text": None, "active": False})
    
    return JSONResponse(content=_json_response_content(config.model_dump(by_alias=True)))

@router.get("/api/site-assets")
async def api_list_site_assets():
    """List all active site assets."""
    if SiteAssetService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    service = SiteAssetService()
    assets = await service.list(active=True)
    return JSONResponse(content=_json_response_content({"data": assets, "count": len(assets)}))


@router.get("/api/site-assets/{key}")
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

@router.get("/api/faq")
async def api_list_faq(scope: Optional[str] = None):
    """List active FAQ items, optionally filtered by scope."""
    if FAQItemService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    service = FAQItemService()
    items = await service.list(scope=scope, active=True)
    return JSONResponse(content=_json_response_content({"data": items, "count": len(items)}))


# ========== Public: Collection Slides ==========

@router.get("/api/collection-slides")
async def api_list_collection_slides():
    """List all active collection slides."""
    if CollectionSlideService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    service = CollectionSlideService()
    slides = await service.list(active=True)
    return JSONResponse(content=_json_response_content({"data": slides, "count": len(slides)}))

# ========== Public: Studio, Shop page, Policies ==========

@router.get("/api/studio-settings")
async def api_get_studio_settings():
    if StudioSettingsService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    data = await StudioSettingsService().get_public()
    return JSONResponse(content=_json_response_content({"data": data}))


@router.get("/api/shop-page")
async def api_get_shop_page():
    if ShopPageSettingsService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    data = await ShopPageSettingsService().get_public()
    return JSONResponse(content=_json_response_content({"data": data}))


@router.get("/api/policies")
async def api_get_policies():
    if PolicyContentService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    bundle = await PolicyContentService().get_public_bundle()
    return JSONResponse(content=_json_response_content(bundle))

@router.get("/api/home-page")
async def api_get_home_page():
    if HomePageSettingsService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    data = await HomePageSettingsService().get_public()
    return JSONResponse(content=_json_response_content({"data": data}))


@router.get("/api/story-page")
async def api_get_story_page():
    if StoryPageSettingsService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    data = await StoryPageSettingsService().get_public()
    return JSONResponse(content=_json_response_content({"data": data}))


@router.get("/api/navigation")
async def api_get_navigation():
    if NavigationSettingsService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    data = await NavigationSettingsService().get_public()
    return JSONResponse(content=_json_response_content({"data": data}))


@router.get("/api/contact-page")
async def api_get_contact_page():
    if ContactPageSettingsService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    data = await ContactPageSettingsService().get_public()
    return JSONResponse(content=_json_response_content({"data": data}))


@router.get("/api/account-page")
async def api_get_account_page():
    if AccountPageSettingsService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    data = await AccountPageSettingsService().get_public()
    return JSONResponse(content=_json_response_content({"data": data}))


@router.get("/api/history-page")
async def api_get_history_page():
    if HistoryPageSettingsService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    data = await HistoryPageSettingsService().get_public()
    return JSONResponse(content=_json_response_content({"data": data}))


@router.get("/api/product-page")
async def api_get_product_page():
    if ProductPageSettingsService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    data = await ProductPageSettingsService().get_public()
    return JSONResponse(content=_json_response_content({"data": data}))


@router.get("/api/journal")
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
