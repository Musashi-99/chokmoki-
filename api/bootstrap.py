"""Optional-import bootstrap.

Every app-specific (non-framework, non-stdlib) name the route modules need
is imported here, in one place, behind a single try/except so a broken
import can't crash the whole app at boot — every name gets a `None`
fallback instead. Route modules do `from api.bootstrap import X` rather
than importing from `src.*` directly, so this resilience property doesn't
need to be re-implemented in every router file.
"""
import sys

try:
    from src.database.connection import db
    from src.database.redis_connection import redis_client
    from src.cqrs.router import CQRSRouter
    from src.services.razorpay_service import RazorpayService
    from src.services.order_service import OrderService
    from src.services.telegram_service import TelegramService
    from src.alerts.consumer import AlertConsumer
    from src.plugins.logger import logger
    from src.config import settings
    from src.security.error_handling import register_exception_handlers
    from src.security.mass_assignment import build_update_payload, require_update_fields
    from src.services.fraud_review_service import FraudReviewService
    from src.middleware.correlation_id import CorrelationIdMiddleware
    from src.plugins.rate_limit import RateLimitMiddleware
    from src.plugins.admin_deps import require_admin, require_permission
    from src.plugins.admin_audit_middleware import AdminAuditMiddleware
    from src.plugins.admin_cookies import set_auth_cookies, clear_auth_cookies
    from src.services.product_service import ProductService
    from src.services.category_service import CategoryService
    from src.models.product import JewelryProductCreate, JewelryProductUpdate
    from src.models.category import JewelryCategoryCreate, JewelryCategoryUpdate
    from src.models.order import OrderCreateInput, OrderStatus
    from src.models.admin_rbac import AdminRole
    from src.services.admin_auth_service import AdminAuthService
    from src.services.r2_service import R2Service
    from src.utils.upload_validation import UploadValidationError, validate_upload
    from src.models.testimonial import TestimonialCreate, TestimonialUpdate
    from src.models.hero_config import HeroConfigCreate, HeroConfigUpdate
    from src.services.testimonial_service import TestimonialService
    from src.services.hero_config_service import HeroConfigService
    from src.models.site_asset import SiteAssetCreate, SiteAssetUpdate
    from src.models.faq_item import FAQItemCreate, FAQItemUpdate
    from src.models.collection_slide import CollectionSlideCreate, CollectionSlideUpdate
    from src.services.site_asset_service import SiteAssetService
    from src.services.faq_item_service import FAQItemService
    from src.services.collection_slide_service import CollectionSlideService
    from src.services.studio_settings_service import StudioSettingsService
    from src.services.shop_page_settings_service import ShopPageSettingsService
    from src.services.policy_content_service import PolicyContentService
    from src.models.studio_settings import StudioSettingsUpdate
    from src.models.shop_page_settings import ShopPageSettingsUpdate
    from src.models.policy_content import PolicyPageMetaUpdate, PolicySectionCreate, PolicySectionUpdate
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
    from src.models.blog_post import BlogPostCreate, BlogPostUpdate, JournalPageSettingsUpdate
    from src.models.navigation_settings import NavigationSettingsUpdate
    from src.models.contact_page_settings import ContactPageSettingsUpdate
    from src.models.history_page_settings import HistoryPageSettingsUpdate
    from src.models.product_page_settings import ProductPageSettingsUpdate
    from src.models.inbox import ContactSubmissionCreate, NewsletterSubscribeCreate
    from src.services.cache_service import cache
    from src.security.exceptions import AuthorizationError, MFACodeRequired, AccountLockedError
    from src.security.client_ip import get_client_ip
    from src.plugins.metrics import render_metrics
except Exception as e:
    print(f"Import error: {e}", file=sys.stderr)
    db = None
    redis_client = None
    CQRSRouter = None
    RazorpayService = None
    OrderService = None
    TelegramService = None
    AlertConsumer = None
    logger = None
    settings = None
    RateLimitMiddleware = None
    require_admin = None
    require_permission = None
    AdminAuditMiddleware = None
    set_auth_cookies = None
    clear_auth_cookies = None
    ProductService = None
    CategoryService = None
    JewelryProductCreate = None
    JewelryCategoryCreate = None
    OrderCreateInput = None
    OrderStatus = None
    AdminRole = None
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
    AuthorizationError = None
    MFACodeRequired = None
    AccountLockedError = None
    get_client_ip = None
    render_metrics = None
    register_exception_handlers = None
    CorrelationIdMiddleware = None
    FraudReviewService = None
    build_update_payload = None
    require_update_fields = None
