from typing import Dict, Any, Optional

from pydantic import BaseModel, ValidationError

from src.cqrs.param_models import PARAM_MODELS
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
from src.resources.contacts.queries import (
    ContactListQuery,
)
from src.resources.contacts.mutations import (
    ContactCreateMutation,
)
from src.resources.shipping_addresses.queries import (
    ShippingAddressListQuery,
    ShippingAddressGetQuery,
)
from src.resources.shipping_addresses.mutations import (
    ShippingAddressCreateMutation,
    ShippingAddressUpdateMutation,
    ShippingAddressDeleteMutation,
)
from src.resources.newsletter.mutations import (
    NewsletterSubscribeMutation,
)
from src.resources.sync_key.queries import (
    SyncKeyGetQuery,
)
from src.plugins.admin_auth import validate_admin_key
from src.services.order_service import OrderService
from src.services.shipping_address_service import ShippingAddressService
from src.security.exceptions import AuthorizationError


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
        "newsletter.subscribe": NewsletterSubscribeMutation,
    }

    ADMIN_REQUIRED_OPERATIONS = {
        "product.create",
        "product.update",
        "product.delete",
        "category.create",
        "category.update",
        "category.delete",
        "order.getLog",
        "order.updateStatus",
        "order.list",
        "order.get",
        "shippingAddress.list",
        "shippingAddress.get",
        "shippingAddress.create",
        "shippingAddress.update",
        "shippingAddress.delete",
    }

    @classmethod
    async def _is_admin(cls, admin_key: Optional[str]) -> bool:
        return bool(admin_key and await validate_admin_key(admin_key))

    @classmethod
    async def _require_admin(cls, operation: str, admin_key: Optional[str]) -> None:
        if not await cls._is_admin(admin_key):
            raise AuthorizationError(f"Admin authentication required for {operation}")

    @classmethod
    def _validate_params(cls, operation: str, params: Dict[str, Any]) -> Dict[str, Any]:
        model_cls = PARAM_MODELS.get(operation)
        if model_cls is None:
            return params
        try:
            validated: BaseModel = model_cls.model_validate(params)
        except ValidationError as exc:
            raise ValueError("Invalid request parameters") from exc
        return validated.model_dump(by_alias=True)

    @classmethod
    def _normalized_email(cls, params: Dict[str, Any], key: str) -> str:
        value = params.get(key)
        if not isinstance(value, str):
            return ""
        return value.strip().lower()

    @classmethod
    async def _check_order_get_access(
        cls, params: Dict[str, Any], admin_key: Optional[str]
    ) -> None:
        if await cls._is_admin(admin_key):
            return

        user_email = cls._normalized_email(params, "userEmail")
        order_id = params.get("id")
        if not order_id:
            raise ValueError("Order ID is required")
        if not user_email:
            raise AuthorizationError("Authentication required to view this order")

        order = await OrderService().get_by_id(order_id)
        if not order:
            raise ValueError("Order not found")
        if order.user_email.lower() != user_email:
            raise AuthorizationError("Authentication required to view this order")

    @classmethod
    async def _check_shipping_address_get_access(
        cls, params: Dict[str, Any], admin_key: Optional[str]
    ) -> None:
        if await cls._is_admin(admin_key):
            return

        email = cls._normalized_email(params, "email")
        address_id = params.get("id")
        if not address_id:
            raise ValueError("Address ID is required")
        if not email:
            raise AuthorizationError("Authentication required to view this address")

        address = await ShippingAddressService().get_by_id(address_id)
        if not address:
            raise ValueError("Address not found")
        if address.email.lower() != email:
            raise AuthorizationError("Authentication required to view this address")

    @classmethod
    async def _authorize(
        cls, operation: str, params: Dict[str, Any], admin_key: Optional[str]
    ) -> None:
        if operation in cls.ADMIN_REQUIRED_OPERATIONS:
            await cls._require_admin(operation, admin_key)

        if operation == "order.list":
            user_email = cls._normalized_email(params, "userEmail")
            if not user_email:
                await cls._require_admin(operation, admin_key)

        if operation == "shippingAddress.get":
            await cls._check_shipping_address_get_access(params, admin_key)

        if operation == "contact.list":
            await cls._require_admin(operation, admin_key)

        if operation.startswith("analytics.") and operation not in {
            "analytics.trackEvent",
            "analytics.trackMetric",
        }:
            await cls._require_admin(operation, admin_key)

        if operation == "order.get":
            await cls._check_order_get_access(params, admin_key)

    @classmethod
    async def execute_query(
        cls, operation: str, params: Dict[str, Any], admin_key: Optional[str] = None
    ) -> Dict[str, Any]:
        if operation not in cls.QUERIES:
            raise ValueError(f"Unknown query operation: {operation}")

        validated_params = cls._validate_params(operation, params)
        await cls._authorize(operation, validated_params, admin_key)

        query_class = cls.QUERIES[operation]
        query = query_class()
        return await query.execute(validated_params)

    @classmethod
    async def execute_mutation(
        cls, operation: str, params: Dict[str, Any], admin_key: Optional[str] = None
    ) -> Dict[str, Any]:
        if operation not in cls.MUTATIONS:
            raise ValueError(f"Unknown mutation operation: {operation}")

        validated_params = cls._validate_params(operation, params)
        await cls._authorize(operation, validated_params, admin_key)

        mutation_class = cls.MUTATIONS[operation]
        mutation = mutation_class()
        return await mutation.execute(validated_params)
