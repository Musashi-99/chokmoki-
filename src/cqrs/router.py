from typing import Dict, Any, Optional
from src.resources.products.queries import (
    ProductListQuery,
    ProductGetQuery,
    ProductSearchQuery,
    ProductGetByIdsQuery,
)
from src.resources.products.mutations import (
    ProductCreateMutation,
    ProductUpdateMutation,
    ProductDeleteMutation,
)
from src.resources.categories.queries import (
    CategoryListQuery,
    CategoryGetQuery,
)
from src.resources.categories.mutations import (
    CategoryCreateMutation,
    CategoryUpdateMutation,
    CategoryDeleteMutation,
)
from src.resources.orders.queries import (
    OrderListQuery,
    OrderGetQuery,
    OrderLogQuery,
)
from src.resources.orders.mutations import (
    OrderCreateMutation,
    OrderInitiateMutation,
    OrderVerifyPaymentMutation,
    OrderStatusUpdateMutation,
)
from src.resources.analytics.queries import (
    GetEventsQuery,
    GetUniqueUsersQuery,
    GetEventCountQuery,
    GetRevenueQuery,
    GetTopSearchesQuery,
    GetTopProductsQuery,
    GetAnalyticsOverviewQuery,
)
from src.resources.analytics.mutations import (
    TrackEventMutation,
    TrackMetricMutation,
)
from src.resources.ratings.queries import (
    RatingListQuery,
    RatingSummaryQuery,
    RatingCanRateQuery,
)
from src.resources.ratings.mutations import (
    RatingCreateMutation,
)
from src.cqrs.queries import (
    ShippingAddressListQuery,
    ShippingAddressGetQuery,
    SyncKeyGetQuery,
    ContactListQuery,
)
from src.cqrs.mutations import (
    ContactCreateMutation,
    ShippingAddressCreateMutation,
    ShippingAddressUpdateMutation,
    ShippingAddressDeleteMutation
)
from src.plugins.admin_auth import validate_admin_key


class CQRSRouter:
    QUERIES: Dict[str, Any] = {
        "product.list": ProductListQuery,
        "product.get": ProductGetQuery,
        "product.search": ProductSearchQuery,
        "product.getByIds": ProductGetByIdsQuery,
        "category.list": CategoryListQuery,
        "category.get": CategoryGetQuery,
        "order.list": OrderListQuery,
        "order.get": OrderGetQuery,
        "order.getLog": OrderLogQuery,
        "shippingAddress.list": ShippingAddressListQuery,
        "shippingAddress.get": ShippingAddressGetQuery,
        "syncKey.get": SyncKeyGetQuery,
        "contact.list": ContactListQuery,
        "analytics.events": GetEventsQuery,
        "analytics.uniqueUsers": GetUniqueUsersQuery,
        "analytics.eventCount": GetEventCountQuery,
        "analytics.revenue": GetRevenueQuery,
        "analytics.topSearches": GetTopSearchesQuery,
        "analytics.topProducts": GetTopProductsQuery,
        "analytics.overview": GetAnalyticsOverviewQuery,
        "rating.list": RatingListQuery,
        "rating.summary": RatingSummaryQuery,
        "rating.canRate": RatingCanRateQuery,
    }
    
    MUTATIONS: Dict[str, Any] = {
        "product.create": ProductCreateMutation,
        "product.update": ProductUpdateMutation,
        "product.delete": ProductDeleteMutation,
        "category.create": CategoryCreateMutation,
        "category.update": CategoryUpdateMutation,
        "category.delete": CategoryDeleteMutation,
        "order.create": OrderCreateMutation,
        "order.initiate": OrderInitiateMutation,
        "order.verifyPayment": OrderVerifyPaymentMutation,
        "order.updateStatus": OrderStatusUpdateMutation,
        "contact.create": ContactCreateMutation,
        "shippingAddress.create": ShippingAddressCreateMutation,
        "shippingAddress.update": ShippingAddressUpdateMutation,
        "shippingAddress.delete": ShippingAddressDeleteMutation,
        "analytics.trackEvent": TrackEventMutation,
        "analytics.trackMetric": TrackMetricMutation,
        "rating.create": RatingCreateMutation,
    }
    
    ADMIN_REQUIRED_OPERATIONS = {
        "product.create",
        "product.update",
        "product.delete",
        "category.create",
        "category.update",
        "category.delete",
    }
    
    @classmethod
    def _check_admin_auth(cls, operation: str, params: Dict[str, Any], admin_key: Optional[str] = None) -> None:
        if operation in cls.ADMIN_REQUIRED_OPERATIONS:
            if not admin_key or not validate_admin_key(admin_key):
                raise ValueError("Admin authentication required for this operation")
        
        if operation == "order.list":
            user_email = params.get("userEmail")
            if not user_email:
                if not admin_key or not validate_admin_key(admin_key):
                    raise ValueError("Admin authentication required to list all orders")
        
        if operation == "contact.list":
            if not admin_key or not validate_admin_key(admin_key):
                raise ValueError("Admin authentication required to list contacts")
        
        # Analytics queries require admin authentication (but mutations don't)
        if operation.startswith("analytics.") and operation not in ["analytics.trackEvent", "analytics.trackMetric"]:
            if not admin_key or not validate_admin_key(admin_key):
                raise ValueError("Admin authentication required for analytics operations")
    
    @classmethod
    async def execute_query(cls, operation: str, params: Dict[str, Any], admin_key: Optional[str] = None) -> Dict[str, Any]:
        if operation not in cls.QUERIES:
            raise ValueError(f"Unknown query operation: {operation}")
        
        cls._check_admin_auth(operation, params, admin_key)
        
        query_class = cls.QUERIES[operation]
        query = query_class()
        return await query.execute(params)
    
    @classmethod
    async def execute_mutation(cls, operation: str, params: Dict[str, Any], admin_key: Optional[str] = None) -> Dict[str, Any]:
        if operation not in cls.MUTATIONS:
            raise ValueError(f"Unknown mutation operation: {operation}")
        
        cls._check_admin_auth(operation, params, admin_key)
        
        mutation_class = cls.MUTATIONS[operation]
        mutation = mutation_class()
        return await mutation.execute(params)

