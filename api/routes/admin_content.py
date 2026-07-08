"""Admin CRUD for storefront content (hero, nav, policies, pages, journal, etc)."""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from typing import Any, Dict, List
from urllib.parse import urlparse
import json
import httpx
from api.bootstrap import BlogPostCreate, BlogPostUpdate, BlogService, CollectionSlideCreate, CollectionSlideService, CollectionSlideUpdate, ContactPageSettingsService, ContactPageSettingsUpdate, FAQItemCreate, FAQItemService, FAQItemUpdate, HeroConfigCreate, HeroConfigService, HeroConfigUpdate, HistoryPageSettingsService, HistoryPageSettingsUpdate, HomePageSettingsService, HomePageSettingsUpdate, JournalPageSettingsUpdate, NavigationSettingsService, NavigationSettingsUpdate, PolicyContentService, PolicyPageMetaUpdate, PolicySectionCreate, PolicySectionUpdate, ProductPageSettingsService, ProductPageSettingsUpdate, ShopPageSettingsService, ShopPageSettingsUpdate, SiteAssetCreate, SiteAssetService, SiteAssetUpdate, StoryPageSettingsService, StoryPageSettingsUpdate, StudioSettingsService, StudioSettingsUpdate, TestimonialCreate, TestimonialService, TestimonialUpdate, build_update_payload, require_admin, require_update_fields, settings
from api.json_utils import JSONEncoder, _json_response_content

router = APIRouter()


@router.get("/api/admin/testimonials")
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


@router.post("/api/admin/testimonials")
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


@router.put("/api/admin/testimonials/{testimonial_id}")
async def admin_update_testimonial(
    testimonial_id: str, payload: Dict[str, Any], email: str = Depends(require_admin)
):
    """Update a testimonial by its MongoDB id."""
    if TestimonialService is None or TestimonialUpdate is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    try:
        update_data = build_update_payload(TestimonialUpdate, payload)
        require_update_fields(update_data)
        updated = await TestimonialService().update(testimonial_id, update_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="Testimonial not found")
    return JSONResponse(content=json.loads(json.dumps(
        updated.model_dump(by_alias=True), cls=JSONEncoder
    )))


@router.delete("/api/admin/testimonials/{testimonial_id}")
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

@router.get("/api/admin/hero")
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


@router.post("/api/admin/hero")
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


@router.put("/api/admin/hero/{config_id}")
async def admin_update_hero_config(
    config_id: str, payload: Dict[str, Any], email: str = Depends(require_admin)
):
    """Update a hero config by its MongoDB id."""
    if HeroConfigService is None or HeroConfigCreate is None or HeroConfigUpdate is None:
        raise HTTPException(status_code=500, detail="Server not initialized")

    service = HeroConfigService()
    existing = await service.get_by_id(config_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Hero config not found")

    try:
        update_data = build_update_payload(HeroConfigUpdate, payload)
        require_update_fields(update_data)
        existing_data = existing.model_dump(
            exclude={"_id", "id", "updated_at", "created_at"}
        )
        merged = {**existing_data, **update_data}
        data = HeroConfigCreate(**merged)
        updated = await service.update(config_id, data.model_dump())
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not updated:
        updated = await service.get_by_id(config_id)
    return JSONResponse(content=json.loads(json.dumps(
        updated.model_dump(by_alias=True), cls=JSONEncoder
    )))


@router.delete("/api/admin/hero/{config_id}")
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

@router.get("/api/admin/site-assets")
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


@router.post("/api/admin/site-assets")
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


@router.put("/api/admin/site-assets/{asset_id}")
async def admin_update_site_asset(
    asset_id: str, payload: Dict[str, Any], email: str = Depends(require_admin)
):
    """Update a site asset by its MongoDB id."""
    if SiteAssetService is None or SiteAssetUpdate is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    try:
        update_data = build_update_payload(SiteAssetUpdate, payload)
        require_update_fields(update_data)
        updated = await SiteAssetService().update(asset_id, update_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="Site asset not found")
    return JSONResponse(content=json.loads(json.dumps(
        updated.model_dump(by_alias=True), cls=JSONEncoder
    )))


@router.delete("/api/admin/site-assets/{asset_id}")
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

@router.get("/api/admin/faq")
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


@router.post("/api/admin/faq")
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


@router.put("/api/admin/faq/{faq_id}")
async def admin_update_faq_item(
    faq_id: str, payload: Dict[str, Any], email: str = Depends(require_admin)
):
    """Update a FAQ item by its MongoDB id."""
    if FAQItemService is None or FAQItemUpdate is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    try:
        update_data = build_update_payload(FAQItemUpdate, payload)
        require_update_fields(update_data)
        updated = await FAQItemService().update(faq_id, update_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="FAQ item not found")
    return JSONResponse(content=json.loads(json.dumps(
        updated.model_dump(by_alias=True), cls=JSONEncoder
    )))


@router.delete("/api/admin/faq/{faq_id}")
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

@router.get("/api/admin/collection-slides")
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


@router.post("/api/admin/collection-slides")
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


@router.put("/api/admin/collection-slides/{slide_id}")
async def admin_update_collection_slide(
    slide_id: str, payload: Dict[str, Any], email: str = Depends(require_admin)
):
    """Update a collection slide by its MongoDB id."""
    if CollectionSlideService is None or CollectionSlideUpdate is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    
    try:
        update_data = build_update_payload(CollectionSlideUpdate, payload)
        require_update_fields(update_data)
        updated = await CollectionSlideService().update(slide_id, update_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="Collection slide not found")
    return JSONResponse(content=json.loads(json.dumps(
        updated.model_dump(by_alias=True), cls=JSONEncoder
    )))


@router.delete("/api/admin/collection-slides/{slide_id}")
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

@router.get("/api/admin/studio-settings")
async def admin_get_studio_settings(email: str = Depends(require_admin)):
    if StudioSettingsService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    settings = await StudioSettingsService().get_admin()
    return JSONResponse(content=_json_response_content({
        "data": settings.model_dump(by_alias=True) if settings else None,
    }))


@router.put("/api/admin/studio-settings")
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

@router.get("/api/admin/shop-page")
async def admin_get_shop_page(email: str = Depends(require_admin)):
    if ShopPageSettingsService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    settings = await ShopPageSettingsService().get_admin()
    return JSONResponse(content=_json_response_content({
        "data": settings.model_dump(by_alias=True) if settings else None,
    }))


@router.put("/api/admin/shop-page")
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

@router.get("/api/admin/policies")
async def admin_get_policies(email: str = Depends(require_admin)):
    if PolicyContentService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    bundle = await PolicyContentService().get_admin_bundle()
    return JSONResponse(content=_json_response_content(bundle))


@router.put("/api/admin/policies/meta")
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


@router.get("/api/admin/policies/meta")
async def admin_get_policy_meta(email: str = Depends(require_admin)):
    if PolicyContentService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    bundle = await PolicyContentService().get_admin_bundle()
    return JSONResponse(content=_json_response_content(bundle.get("meta")))


@router.put("/api/admin/policies/sections/{slug}")
async def admin_upsert_policy_section(
    slug: str, payload: Dict[str, Any], email: str = Depends(require_admin)
):
    if PolicyContentService is None or PolicySectionUpdate is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    try:
        update_data = build_update_payload(PolicySectionUpdate, payload)
        require_update_fields(update_data)
        updated = await PolicyContentService().upsert_section_by_slug(slug, update_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return JSONResponse(content=json.loads(json.dumps(
        updated.model_dump(by_alias=True), cls=JSONEncoder
    )))


@router.post("/api/admin/policies/sections")
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


@router.delete("/api/admin/policies/sections/{slug}")
async def admin_delete_policy_section(
    slug: str, email: str = Depends(require_admin)
):
    if PolicyContentService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    deleted = await PolicyContentService().delete_section_by_slug(slug)
    if not deleted:
        raise HTTPException(status_code=404, detail="Policy section not found")
    return JSONResponse(content={"success": True, "slug": slug})

@router.get("/api/admin/home-page")
async def admin_get_home_page(email: str = Depends(require_admin)):
    if HomePageSettingsService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    settings = await HomePageSettingsService().get_admin()
    return JSONResponse(content=_json_response_content({
        "data": settings.model_dump(by_alias=True) if settings else None,
    }))


@router.put("/api/admin/home-page")
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


@router.get("/api/admin/story-page")
async def admin_get_story_page(email: str = Depends(require_admin)):
    if StoryPageSettingsService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    settings = await StoryPageSettingsService().get_admin()
    return JSONResponse(content=_json_response_content({
        "data": settings.model_dump(by_alias=True) if settings else None,
    }))


@router.put("/api/admin/story-page")
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


@router.get("/api/admin/navigation")
async def admin_get_navigation(email: str = Depends(require_admin)):
    if NavigationSettingsService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    settings = await NavigationSettingsService().get_admin()
    return JSONResponse(content=_json_response_content({
        "data": settings.model_dump(by_alias=True) if settings else None,
    }))


@router.put("/api/admin/navigation")
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


@router.get("/api/admin/contact-page")
async def admin_get_contact_page(email: str = Depends(require_admin)):
    if ContactPageSettingsService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    settings = await ContactPageSettingsService().get_admin()
    return JSONResponse(content=_json_response_content({
        "data": settings.model_dump(by_alias=True) if settings else None,
    }))


@router.put("/api/admin/contact-page")
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


@router.get("/api/admin/history-page")
async def admin_get_history_page(email: str = Depends(require_admin)):
    if HistoryPageSettingsService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    settings = await HistoryPageSettingsService().get_admin()
    return JSONResponse(content=_json_response_content({
        "data": settings.model_dump(by_alias=True) if settings else None,
    }))


@router.put("/api/admin/history-page")
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


@router.get("/api/admin/product-page")
async def admin_get_product_page(email: str = Depends(require_admin)):
    if ProductPageSettingsService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    settings = await ProductPageSettingsService().get_admin()
    return JSONResponse(content=_json_response_content({
        "data": settings.model_dump(by_alias=True) if settings else None,
    }))


@router.put("/api/admin/product-page")
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

@router.get("/api/admin/journal")
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


@router.put("/api/admin/journal/meta")
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


@router.get("/api/admin/journal/meta")
async def admin_get_journal_meta(email: str = Depends(require_admin)):
    if BlogService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    meta = await BlogService().get_journal_admin()
    return JSONResponse(content=_json_response_content(
        meta.model_dump(by_alias=True) if meta else None
    ))


@router.post("/api/admin/blog-posts")
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


@router.put("/api/admin/blog-posts/{post_id}")
async def admin_update_blog_post(
    post_id: str, payload: Dict[str, Any], email: str = Depends(require_admin)
):
    if BlogService is None or BlogPostUpdate is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    try:
        update_data = build_update_payload(BlogPostUpdate, payload)
        require_update_fields(update_data)
        updated = await BlogService().update_post(post_id, update_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="Blog post not found")
    return JSONResponse(content=json.loads(json.dumps(
        updated.model_dump(by_alias=True), cls=JSONEncoder
    )))


@router.delete("/api/admin/blog-posts/{post_id}")
async def admin_delete_blog_post(post_id: str, email: str = Depends(require_admin)):
    if BlogService is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    deleted = await BlogService().delete_post(post_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Blog post not found")
    return {"success": True}


ASSET_PROXY_ALLOWED_HOSTS = {"cdn.amplifycheckout.com", "images.unsplash.com"}


@router.get("/api/admin/asset-proxy")
async def admin_asset_proxy(url: str, email: str = Depends(require_admin)):
    """Stream a content asset (product/category image or video) server-side.

    The full site-content export runs in the browser, and the CDN does not send
    CORS headers, so a direct `fetch()` from the admin app fails for every
    asset. Proxying through the API (same origin as the admin app, no browser
    CORS check) lets the export actually capture the real images/videos.
    Restricted to known CDN hosts to avoid becoming an open SSRF proxy.
    """
    host = urlparse(url).hostname or ""
    if host not in ASSET_PROXY_ALLOWED_HOSTS:
        raise HTTPException(status_code=400, detail="Asset host not allowed")

    client = httpx.AsyncClient(timeout=30.0)
    req = client.build_request("GET", url)
    resp = await client.send(req, stream=True)
    if resp.status_code != 200:
        await resp.aclose()
        await client.aclose()
        raise HTTPException(status_code=502, detail=f"Upstream {resp.status_code}")

    async def stream():
        try:
            async for chunk in resp.aiter_bytes():
                yield chunk
        finally:
            await resp.aclose()
            await client.aclose()

    return StreamingResponse(
        stream(),
        media_type=resp.headers.get("content-type", "application/octet-stream"),
    )
